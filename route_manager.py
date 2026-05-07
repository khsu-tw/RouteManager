"""
RouteManager - 以路由表方式，讓特定 IP 走指定網卡
不使用 Proxy，OS 層級直接分流，Outlook/Teams 等程式完全不受影響
Windows 需以「系統管理員」身分執行
macOS/Linux 需以 sudo 執行
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 修復 Windows 終端機編碼
if sys.platform == 'win32':
    import ctypes
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.system('chcp 65001 > nul 2>&1')

CONFIG_FILE = Path(__file__).parent / "route_config.json"


def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_admin():
    """檢查是否有管理員/root 權限"""
    if sys.platform == 'win32':
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False
    else:
        # macOS/Linux: 檢查是否為 root
        return os.geteuid() == 0


def run_ps(ps_cmd):
    """執行 PowerShell 命令並回傳 stdout (Windows only)"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    return result.stdout


def get_network_adapters():
    """取得所有具 Gateway 的網卡"""
    adapters = []

    if sys.platform == 'win32':
        # Windows: 使用 PowerShell
        ps_cmd = '''
        Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | ForEach-Object {
            [PSCustomObject]@{
                Name = $_.InterfaceAlias
                Index = $_.InterfaceIndex
                IP = $_.IPv4Address.IPAddress
                Gateway = $_.IPv4DefaultGateway.NextHop
            }
        } | ConvertTo-Json
        '''
        try:
            data = json.loads(run_ps(ps_cmd))
            if isinstance(data, dict):
                data = [data]
            for item in data:
                adapters.append({
                    'name': item['Name'],
                    'index': int(item['Index']),
                    'ip': item['IP'],
                    'gateway': item['Gateway']
                })
        except:
            pass

    elif sys.platform == 'darwin':
        # macOS: 使用 networksetup
        try:
            result = subprocess.run(
                ["networksetup", "-listallnetworkservices"],
                capture_output=True, text=True
            )
            services = [line for line in result.stdout.strip().split('\n')
                       if line and not line.startswith('*')]

            for service in services:
                # 取得網路介面名稱 (en0, en1, etc.)
                result = subprocess.run(
                    ["networksetup", "-listallhardwareports"],
                    capture_output=True, text=True
                )
                interface = None
                lines = result.stdout.split('\n')
                for i, line in enumerate(lines):
                    if service in line:
                        for j in range(i+1, min(i+3, len(lines))):
                            if lines[j].startswith('Device:'):
                                interface = lines[j].split(':')[1].strip()
                                break
                        break

                # 取得 IP 和 Gateway
                result = subprocess.run(
                    ["networksetup", "-getinfo", service],
                    capture_output=True, text=True
                )
                info = result.stdout
                ip = None
                gateway = None

                for line in info.split('\n'):
                    if line.startswith('IP address:'):
                        ip = line.split(':')[1].strip()
                    elif line.startswith('Router:'):
                        gw = line.split(':')[1].strip()
                        if gw and gw != 'none':
                            gateway = gw

                if ip and gateway and ip != 'none' and interface:
                    adapters.append({
                        'name': service,
                        'index': interface,  # macOS 用 interface name
                        'ip': ip,
                        'gateway': gateway
                    })
        except:
            pass

    else:
        # Linux: 使用 ip 命令
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().split('\n'):
                if 'default via' in line:
                    parts = line.split()
                    gateway = parts[2]
                    iface = parts[4]

                    result2 = subprocess.run(
                        ["ip", "-4", "addr", "show", iface],
                        capture_output=True, text=True
                    )
                    for addr_line in result2.stdout.split('\n'):
                        if 'inet ' in addr_line:
                            ip = addr_line.strip().split()[1].split('/')[0]
                            adapters.append({
                                'name': iface,
                                'index': iface,
                                'ip': ip,
                                'gateway': gateway
                            })
                            break
        except:
            pass

    return adapters


def load_config():
    default = {
        "hotspot_adapter": None,
        "routes": [],          # ["1.34.56.127", ...]   僅支援 IP (路由表不吃 port)
        "persistent": False    # True = route -p，關機後仍保留
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                default.update(cfg)
        except:
            pass
    return default


def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def route_exists(ip):
    """檢查路由表中是否已有此 IP (/32) 的路由"""
    if sys.platform == 'win32':
        result = subprocess.run(
            ["route", "print", ip],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == ip and parts[1] == "255.255.255.255":
                return True
        return False

    elif sys.platform == 'darwin':
        # macOS: route -n get <ip>
        result = subprocess.run(
            ["route", "-n", "get", ip],
            capture_output=True, text=True
        )
        # 如果是 host route，會顯示 "destination: <ip>"
        return result.returncode == 0 and ip in result.stdout

    else:
        # Linux: ip route show <ip>
        result = subprocess.run(
            ["ip", "route", "show", ip],
            capture_output=True, text=True
        )
        return bool(result.stdout.strip())


def add_route(ip, adapter, persistent=False):
    """新增一條 Host Route 指向指定網卡"""
    # 先清掉舊的
    if route_exists(ip):
        delete_route(ip)

    if sys.platform == 'win32':
        cmd = ["route"]
        if persistent:
            cmd.append("-p")
        cmd += ["add", ip, "mask", "255.255.255.255",
                adapter['gateway'],
                "metric", "1",
                "if", str(adapter['index'])]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='ignore')
        ok = result.returncode == 0 and "OK" in (result.stdout or "").upper()
        return ok, (result.stdout or "") + (result.stderr or "")

    elif sys.platform == 'darwin':
        # macOS: route add -host <ip> -interface <interface>
        # 或 route add -host <ip> <gateway>
        cmd = ["route", "add", "-host", ip, adapter['gateway']]
        result = subprocess.run(cmd, capture_output=True, text=True)
        ok = result.returncode == 0 or "add host" in (result.stdout or "").lower()
        msg = (result.stdout or "") + (result.stderr or "")

        # macOS 沒有內建 persistent route，需寫入 launchd plist
        if persistent and ok:
            msg += " (Note: macOS persistent routes need manual launchd setup)"

        return ok, msg

    else:
        # Linux: ip route add <ip> via <gateway> dev <interface>
        cmd = ["ip", "route", "add", ip, "via", adapter['gateway'], "dev", adapter['index']]
        result = subprocess.run(cmd, capture_output=True, text=True)
        ok = result.returncode == 0
        msg = (result.stdout or "") + (result.stderr or "")

        if persistent and ok:
            msg += " (Note: Linux persistent routes need /etc/network/interfaces or netplan)"

        return ok, msg


def delete_route(ip):
    """刪除路由"""
    if sys.platform == 'win32':
        result = subprocess.run(
            ["route", "delete", ip],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )
        return result.returncode == 0, (result.stdout or "") + (result.stderr or "")

    elif sys.platform == 'darwin':
        # macOS
        result = subprocess.run(
            ["route", "delete", "-host", ip],
            capture_output=True, text=True
        )
        return result.returncode == 0, (result.stdout or "") + (result.stderr or "")

    else:
        # Linux
        result = subprocess.run(
            ["ip", "route", "del", ip],
            capture_output=True, text=True
        )
        return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def apply_all_routes(config):
    """把 config.routes 內所有 IP 全部套用到路由表"""
    adapter = config.get('hotspot_adapter')
    if not adapter:
        print("\n[!] Please select hotspot adapter first")
        return

    routes = config.get('routes', [])
    if not routes:
        print("\n[!] No routes configured")
        return

    persistent = config.get('persistent', False)
    print(f"\n[{timestamp()}] Applying {len(routes)} route(s) via "
          f"[{adapter['name']}] gw={adapter['gateway']} "
          f"{'(persistent)' if persistent else '(session only)'}")

    for ip in routes:
        ok, msg = add_route(ip, adapter, persistent)
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {ip} -> {adapter['name']}")
        if not ok:
            print(f"         {msg.strip()}")


def clear_all_routes(config):
    """移除所有已套用的路由"""
    routes = config.get('routes', [])
    if not routes:
        print("\n[!] No routes configured")
        return

    print(f"\n[{timestamp()}] Removing {len(routes)} route(s)")
    for ip in routes:
        ok, _ = delete_route(ip)
        status = "OK" if ok else "SKIP"
        print(f"  [{status}] {ip}")


def show_current_routes(config):
    """顯示路由表中與 config 相關的項目"""
    routes = config.get('routes', [])
    if not routes:
        print("\n[!] No routes configured")
        return

    print(f"\n--- Current routing status ---")
    for ip in routes:
        exists = route_exists(ip)
        mark = "ACTIVE" if exists else "NOT SET"
        print(f"  [{mark}] {ip}")


def test_route(config):
    """測試特定 IP 走哪張網卡"""
    ip = input("\nEnter IP to test (e.g., 1.34.56.127): ").strip()
    if not ip:
        return

    if sys.platform == 'win32':
        print(f"\n--- tracert -h 2 {ip} ---")
        subprocess.run(["tracert", "-h", "2", "-w", "2000", ip])
    else:
        # macOS/Linux 用 traceroute
        print(f"\n--- traceroute -m 2 {ip} ---")
        subprocess.run(["traceroute", "-m", "2", "-w", "2", ip])

    print(f"\n--- Expected gateway ---")
    adapter = config.get('hotspot_adapter')
    if adapter:
        print(f"If routed via hotspot: {adapter['gateway']}")

    input("\nPress Enter to continue...")


def setup_menu():
    config = load_config()

    while True:
        print("\n" + "="*50)
        print("       RouteManager - Settings")
        print("="*50)

        adapter = config.get('hotspot_adapter')
        if adapter:
            print(f"\nHotspot: {adapter['name']}  "
                  f"IP={adapter['ip']}  GW={adapter['gateway']}")
        else:
            print("\nHotspot: Not set")

        print(f"Persistent: {'Yes (-p)' if config.get('persistent') else 'No (session only)'}")

        routes = config.get('routes', [])
        if routes:
            print(f"\nRoutes ({len(routes)}):")
            for i, ip in enumerate(routes, 1):
                active = "ACTIVE" if route_exists(ip) else "       "
                print(f"  {i}. [{active}] {ip}")

        print("\nOptions:")
        print("  1. Select hotspot adapter")
        print("  2. Add IP to route via hotspot")
        print("  3. Remove IP")
        print("  4. Toggle persistent mode")
        print("  5. Apply all routes NOW")
        print("  6. Clear all routes NOW")
        print("  7. Show current routing status")
        print("  8. Test route (tracert)")
        print("  0. Exit")

        choice = input("\nSelect [0-8]: ").strip()

        if choice == '1':
            adapters = get_network_adapters()
            if not adapters:
                print("\nNo network adapters found")
                continue
            print("\nAvailable adapters:")
            for i, a in enumerate(adapters, 1):
                print(f"  {i}. {a['name']}")
                print(f"     IP={a['ip']}  GW={a['gateway']}  if={a['index']}")
            try:
                idx = int(input("\nSelect adapter: ")) - 1
                if 0 <= idx < len(adapters):
                    config['hotspot_adapter'] = adapters[idx]
                    save_config(config)
                    print(f"\nSelected: {adapters[idx]['name']}")
            except ValueError:
                pass

        elif choice == '2':
            ip = input("\nEnter IP (e.g., 1.34.56.127): ").strip()
            if ip and ip not in config.get('routes', []):
                config.setdefault('routes', []).append(ip)
                save_config(config)
                print(f"\nAdded: {ip}")
            else:
                print("\nInvalid or duplicate")

        elif choice == '3':
            routes = config.get('routes', [])
            if not routes:
                print("\nNo routes")
                continue
            print("\nRoutes:")
            for i, ip in enumerate(routes, 1):
                print(f"  {i}. {ip}")
            try:
                idx = int(input("\nSelect to remove (0 to cancel): ")) - 1
                if 0 <= idx < len(routes):
                    removed = routes.pop(idx)
                    # 同時從路由表移除
                    if route_exists(removed):
                        delete_route(removed)
                    save_config(config)
                    print(f"\nRemoved: {removed}")
            except:
                pass

        elif choice == '4':
            config['persistent'] = not config.get('persistent', False)
            save_config(config)
            print(f"\nPersistent: {config['persistent']}")

        elif choice == '5':
            apply_all_routes(config)

        elif choice == '6':
            clear_all_routes(config)

        elif choice == '7':
            show_current_routes(config)

        elif choice == '8':
            test_route(config)

        elif choice == '0':
            print("\nBye!")
            break


def main():
    print("\n" + "="*50)
    print("       RouteManager v1.0")
    print("="*50)

    if not is_admin():
        if sys.platform == 'win32':
            print("\n[!] This tool requires Administrator privileges")
            print("    Please right-click and 'Run as administrator'")
        else:
            print("\n[!] This tool requires root privileges")
            print("    Please run with: sudo python3 route_manager.py")
        input("\nPress Enter to exit...")
        return

    # 預設加入用戶指定的路由
    config = load_config()
    if not config.get('routes'):
        config['routes'] = ['1.34.56.127']
        save_config(config)
        print("\nDefault route added: 1.34.56.127")

    setup_menu()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[Error] {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
