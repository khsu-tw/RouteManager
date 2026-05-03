"""
RouteManager - 以 Windows 路由表方式，讓特定 IP 走指定網卡
不使用 Proxy，OS 層級直接分流，Outlook/Teams 等程式完全不受影響
需以「系統管理員」身分執行
"""

import ctypes
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 修復 Windows 終端機編碼
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.system('chcp 65001 > nul 2>&1')

CONFIG_FILE = Path(__file__).parent / "route_config.json"


def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_admin():
    """檢查是否以系統管理員身分執行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def run_ps(ps_cmd):
    """執行 PowerShell 命令並回傳 stdout"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    return result.stdout


def get_network_adapters():
    """取得所有具 Gateway 的網卡 (包含 InterfaceIndex)"""
    adapters = []
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
    result = subprocess.run(
        ["route", "print", ip],
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    # 如果路由存在，輸出會包含該 IP + mask 255.255.255.255
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == ip and parts[1] == "255.255.255.255":
            return True
    return False


def add_route(ip, adapter, persistent=False):
    """新增一條 Host Route (mask 255.255.255.255) 指向指定網卡"""
    # 先清掉舊的 (避免有殘留指向其他 gateway)
    if route_exists(ip):
        subprocess.run(["route", "delete", ip],
                       capture_output=True, text=True)

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


def delete_route(ip):
    result = subprocess.run(
        ["route", "delete", ip],
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
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

    print(f"\n--- tracert -h 2 {ip} ---")
    subprocess.run(["tracert", "-h", "2", "-w", "2000", ip])

    print(f"\n--- pathping candidate adapter ---")
    adapter = config.get('hotspot_adapter')
    if adapter:
        print(f"Expected gateway if routed via hotspot: {adapter['gateway']}")

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
        print("\n[!] This tool requires Administrator privileges")
        print("    Please right-click and 'Run as administrator'")
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
