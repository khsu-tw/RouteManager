"""
ProxyRouter - HTTP/HTTPS 代理伺服器
讓特定 IP:Port 透過指定網卡連線
"""

import socket
import threading
import select
import json
import os
import sys
import subprocess
import signal
from datetime import datetime
from pathlib import Path

# 修復 Windows 終端機編碼
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.system('chcp 65001 > nul 2>&1')

CONFIG_FILE = Path(__file__).parent / "proxy_config.json"
BUFFER_SIZE = 8192


def timestamp():
    """取得當前時間戳記"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_network_adapters():
    """取得所有網路介面卡資訊"""
    adapters = []

    if sys.platform == 'win32':
        # Windows: 使用 PowerShell
        ps_cmd = '''
        Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | ForEach-Object {
            [PSCustomObject]@{
                Name = $_.InterfaceAlias
                IP = $_.IPv4Address.IPAddress
                Gateway = $_.IPv4DefaultGateway.NextHop
            }
        } | ConvertTo-Json
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, encoding='utf-8', errors='ignore'
        )
        try:
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                adapters.append({
                    'name': item['Name'],
                    'ip': item['IP'],
                    'gateway': item['Gateway']
                })
        except:
            pass

    elif sys.platform == 'darwin':
        # macOS: 使用 networksetup 和 ifconfig
        try:
            # 取得所有網路服務
            result = subprocess.run(
                ["networksetup", "-listallnetworkservices"],
                capture_output=True, text=True
            )
            services = [line for line in result.stdout.strip().split('\n')
                       if line and not line.startswith('*')]

            for service in services:
                # 取得該服務的網路介面名稱
                result = subprocess.run(
                    ["networksetup", "-getinfo", service],
                    capture_output=True, text=True
                )
                info = result.stdout

                # 解析 IP 和 Gateway
                ip = None
                gateway = None
                for line in info.split('\n'):
                    if line.startswith('IP address:'):
                        ip = line.split(':')[1].strip()
                    elif line.startswith('Router:'):
                        gw = line.split(':')[1].strip()
                        if gw and gw != 'none':
                            gateway = gw

                # 只加入有 IP 和 Gateway 的介面
                if ip and gateway and ip != 'none':
                    adapters.append({
                        'name': service,
                        'ip': ip,
                        'gateway': gateway
                    })
        except:
            pass

    else:
        # Linux: 使用 ip 命令
        try:
            # 取得預設路由的介面
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True
            )

            # 解析每個預設路由
            for line in result.stdout.strip().split('\n'):
                if 'default via' in line:
                    parts = line.split()
                    gateway = parts[2]
                    iface = parts[4]

                    # 取得該介面的 IP
                    result2 = subprocess.run(
                        ["ip", "-4", "addr", "show", iface],
                        capture_output=True, text=True
                    )
                    for addr_line in result2.stdout.split('\n'):
                        if 'inet ' in addr_line:
                            ip = addr_line.strip().split()[1].split('/')[0]
                            adapters.append({
                                'name': iface,
                                'ip': ip,
                                'gateway': gateway
                            })
                            break
        except:
            pass

    return adapters


def load_config():
    """載入設定"""
    default = {
        "proxy_port": 8888,
        "hotspot_adapter": None,
        "routes": []  # [{"ip": "1.34.56.127", "port": 5000}]
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
    """儲存設定"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class ProxyHandler(threading.Thread):
    """處理單一連線的代理"""

    def __init__(self, client_socket, client_addr, config):
        super().__init__()
        self.client = client_socket
        self.client_addr = client_addr
        self.config = config
        self.daemon = True

    def should_use_hotspot(self, host, port):
        """檢查是否應該使用熱點"""
        for route in self.config.get('routes', []):
            if route['ip'] == host and route['port'] == port:
                return True
        return False

    def create_connection(self, host, port):
        """建立到目標的連線，根據規則選擇網卡"""
        use_hotspot = self.should_use_hotspot(host, port)
        adapter = self.config.get('hotspot_adapter')

        if use_hotspot and adapter and adapter.get('ip'):
            # 嘗試透過熱點連線
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(30)
                sock.bind((adapter['ip'], 0))
                sock.connect((host, port))
                print(f"[{timestamp()}] -> [{adapter['name']}] {host}:{port}")
                return sock
            except Exception as e:
                print(f"[{timestamp()}] [!] Hotspot failed: {e}, fallback to default")
                try:
                    sock.close()
                except:
                    pass

        # 使用預設網路連線
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((host, port))
        if use_hotspot:
            print(f"[{timestamp()}] -> [Default] {host}:{port} (fallback)")
        return sock

    def run(self):
        try:
            # 接收客戶端請求
            request = self.client.recv(BUFFER_SIZE)
            if not request:
                return

            # 解析請求
            first_line = request.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            parts = first_line.split()

            if len(parts) < 2:
                return

            method = parts[0]
            url = parts[1]

            if method == 'CONNECT':
                # HTTPS 請求
                self.handle_connect(url)
            else:
                # HTTP 請求
                self.handle_http(request, url)

        except Exception as e:
            pass
        finally:
            try:
                self.client.close()
            except:
                pass

    def handle_connect(self, url):
        """處理 HTTPS CONNECT 請求"""
        try:
            host, port = url.split(':')
            port = int(port)
        except:
            host = url
            port = 443

        try:
            # 連線到目標伺服器
            server = self.create_connection(host, port)

            # 回應客戶端連線成功
            self.client.send(b'HTTP/1.1 200 Connection Established\r\n\r\n')

            # 雙向轉發資料
            self.tunnel(self.client, server)

        except Exception as e:
            self.client.send(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')

    def handle_http(self, request, url):
        """處理 HTTP 請求"""
        try:
            # 解析 URL
            if url.startswith('http://'):
                url = url[7:]

            if '/' in url:
                host_port, path = url.split('/', 1)
                path = '/' + path
            else:
                host_port = url
                path = '/'

            if ':' in host_port:
                host, port = host_port.split(':')
                port = int(port)
            else:
                host = host_port
                port = 80

            # 連線到目標伺服器
            server = self.create_connection(host, port)

            # 修改請求（移除完整 URL，改為相對路徑）
            first_line = request.split(b'\r\n')[0]
            new_first_line = first_line.replace(url.encode(), path.encode())
            request = request.replace(first_line, new_first_line, 1)

            # 發送請求
            server.send(request)

            # 接收並轉發回應
            while True:
                data = server.recv(BUFFER_SIZE)
                if not data:
                    break
                self.client.send(data)

            server.close()

        except Exception as e:
            self.client.send(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')

    def tunnel(self, client, server):
        """建立雙向通道"""
        sockets = [client, server]
        try:
            while True:
                readable, _, error = select.select(sockets, [], sockets, 60)

                if error:
                    break

                for sock in readable:
                    data = sock.recv(BUFFER_SIZE)
                    if not data:
                        return

                    if sock is client:
                        server.send(data)
                    else:
                        client.send(data)
        except:
            pass
        finally:
            try:
                server.close()
            except:
                pass


class ProxyServer:
    """代理伺服器"""

    def __init__(self, config):
        self.config = config
        self.running = False
        self.server = None

    def start(self):
        """啟動伺服器"""
        port = self.config.get('proxy_port', 8888)

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.settimeout(1.0)  # 設定 timeout 讓 Ctrl+C 可以中斷
        self.server.bind(('127.0.0.1', port))
        self.server.listen(100)

        self.running = True

        # 設定 Ctrl+C 處理
        def signal_handler(_sig, _frame):
            print(f"\n[{timestamp()}] Stopping...")
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)

        print(f"\n[{timestamp()}] Proxy started on 127.0.0.1:{port}")
        print(f"     Browser proxy settings: 127.0.0.1:{port}")

        if self.config.get('routes'):
            print(f"\n     Routes via hotspot:")
            for r in self.config['routes']:
                print(f"       - {r['ip']}:{r['port']}")

        print("\n     Press Ctrl+C to stop\n")

        while self.running:
            try:
                client, addr = self.server.accept()
                handler = ProxyHandler(client, addr, self.config)
                handler.start()
            except socket.timeout:
                continue  # timeout 後繼續檢查 running 狀態
            except OSError:
                break  # socket 已關閉

        self.stop()

    def stop(self):
        """停止伺服器"""
        self.running = False
        if self.server:
            try:
                self.server.close()
            except:
                pass
        print(f"[{timestamp()}] Proxy stopped")


def test_connection(config):
    """測試連線功能"""
    target = input("\nEnter IP:Port to test (e.g., 1.34.56.127:5000): ").strip()
    if not target or ':' not in target:
        print("Invalid format")
        return

    try:
        ip, port = target.rsplit(':', 1)
        port = int(port)
    except:
        print("Invalid format")
        return

    adapter = config.get('hotspot_adapter')

    print(f"\n--- Testing connection to {ip}:{port} ---\n")

    # 測試 1: 透過預設網路
    print("[Test 1] Default network (no bind)...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((ip, port))
        sock.close()
        print(f"  [OK] Connected via default network")
    except Exception as e:
        print(f"  [FAIL] {e}")

    # 測試 2: 透過熱點網卡
    if adapter and adapter.get('ip'):
        print(f"\n[Test 2] Hotspot ({adapter['name']} - {adapter['ip']})...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.bind((adapter['ip'], 0))
            sock.connect((ip, port))
            sock.close()
            print(f"  [OK] Connected via hotspot")
        except Exception as e:
            print(f"  [FAIL] {e}")
    else:
        print("\n[Test 2] Hotspot not configured, skipped")

    # 測試 3: 列出所有網卡並測試
    print("\n[Test 3] All adapters...")
    adapters = get_network_adapters()
    for a in adapters:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.bind((a['ip'], 0))
            sock.connect((ip, port))
            sock.close()
            print(f"  [OK] {a['name']} ({a['ip']})")
        except Exception as e:
            print(f"  [FAIL] {a['name']} ({a['ip']}): {e}")

    print("\n--- Test complete ---")
    input("\nPress Enter to continue...")


def setup_menu():
    """設定選單"""
    config = load_config()

    while True:
        print("\n" + "="*50)
        print("       ProxyRouter - Settings")
        print("="*50)

        # 顯示目前設定
        print(f"\nProxy Port: {config.get('proxy_port', 8888)}")

        adapter = config.get('hotspot_adapter')
        if adapter:
            print(f"Hotspot: {adapter['name']} ({adapter['ip']})")
        else:
            print("Hotspot: Not set")

        routes = config.get('routes', [])
        if routes:
            print(f"\nRoutes ({len(routes)}):")
            for i, r in enumerate(routes, 1):
                print(f"  {i}. {r['ip']}:{r['port']}")

        print("\nOptions:")
        print("  1. Select hotspot adapter")
        print("  2. Add route (IP:Port)")
        print("  3. Remove route")
        print("  4. Change proxy port")
        print("  5. Start proxy server")
        print("  6. Test connection")
        print("  0. Exit")

        choice = input("\nSelect [0-6]: ").strip()

        if choice == '1':
            adapters = get_network_adapters()
            if not adapters:
                print("\nNo network adapters found")
                continue

            print("\nAvailable adapters:")
            for i, a in enumerate(adapters, 1):
                print(f"  {i}. {a['name']}")
                print(f"     IP: {a['ip']}")

            try:
                idx = int(input("\nSelect adapter: ")) - 1
                if 0 <= idx < len(adapters):
                    config['hotspot_adapter'] = adapters[idx]
                    save_config(config)
                    print(f"\nSelected: {adapters[idx]['name']}")
            except ValueError:
                pass

        elif choice == '2':
            target = input("\nEnter IP:Port (e.g., 1.34.56.127:5000): ").strip()
            try:
                if ':' in target:
                    ip, port = target.rsplit(':', 1)
                    port = int(port)

                    # 檢查重複
                    existing = [(r['ip'], r['port']) for r in config.get('routes', [])]
                    if (ip, port) not in existing:
                        config.setdefault('routes', []).append({'ip': ip, 'port': port})
                        save_config(config)
                        print(f"\nAdded: {ip}:{port}")
                    else:
                        print("\nRoute already exists")
                else:
                    print("\nInvalid format. Use IP:Port")
            except:
                print("\nInvalid input")

        elif choice == '3':
            routes = config.get('routes', [])
            if not routes:
                print("\nNo routes")
                continue

            print("\nRoutes:")
            for i, r in enumerate(routes, 1):
                print(f"  {i}. {r['ip']}:{r['port']}")

            try:
                idx = int(input("\nSelect to remove (0 to cancel): ")) - 1
                if 0 <= idx < len(routes):
                    removed = routes.pop(idx)
                    save_config(config)
                    print(f"\nRemoved: {removed['ip']}:{removed['port']}")
            except:
                pass

        elif choice == '4':
            try:
                port = int(input(f"\nNew port (current: {config.get('proxy_port', 8888)}): "))
                if 1024 <= port <= 65535:
                    config['proxy_port'] = port
                    save_config(config)
                    print(f"\nPort set to: {port}")
                else:
                    print("\nPort must be 1024-65535")
            except:
                pass

        elif choice == '5':
            if not config.get('hotspot_adapter'):
                print("\nPlease select hotspot adapter first")
                continue

            proxy = ProxyServer(config)
            proxy.start()

        elif choice == '6':
            test_connection(config)

        elif choice == '0':
            print("\nBye!")
            break


def main():
    print("\n" + "="*50)
    print("       ProxyRouter v1.0")
    print("="*50)

    # 預設加入用戶指定的路由
    config = load_config()

    # 如果沒有設定，加入預設路由
    if not config.get('routes'):
        config['routes'] = [{'ip': '1.34.56.127', 'port': 5000}]
        save_config(config)
        print("\nDefault route added: 1.34.56.127:5000")

    setup_menu()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[Error] {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
