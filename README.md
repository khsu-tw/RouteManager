# RouteManager

讓特定 IP 透過指定網卡（如行動熱點）連線，其餘流量維持走預設網卡。
提供兩種實作方式，依情境選用。

---

## 方案比較

| 項目 | ProxyRouter (應用層 Proxy) | RouteManager (OS 路由表) |
|---|---|---|
| 分流層級 | HTTP/HTTPS Proxy | Windows 路由表 |
| 需設系統 Proxy | 是 | **否** |
| 對 Outlook / Teams 影響 | 會（因為被迫走 Proxy） | **無** |
| 管理員權限 | 不需要 | **需要** |
| 可依 Port 分流 | 可 (`IP:Port`) | 否（只能依目的 IP） |
| 重開機後保留 | 否 | 可選 (`-p` 持久模式) |

**建議**：一般情境用 RouteManager 最乾淨；若需以 port 區分或無法取得 admin，才用 ProxyRouter。

---

## RouteManager (推薦)

### 使用方式

1. 雙擊 `start_route.bat`（會自動請求系統管理員權限）
2. 選擇 **1** - 選擇熱點網卡
3. 選擇 **2** - 新增要走熱點的 IP（例如 `1.34.56.127`）
4. 選擇 **5** - 套用路由

套用後任何程式（瀏覽器、命令列、自家程式…）連到該 IP 都會走熱點，其他流量（Outlook、Teams、OneDrive…）不受影響。

### 清除路由

- 選擇 **6** 手動清除；或
- 直接重開機（預設為 session only，非持久）

### 持久模式

選擇 **4** 切換成 Persistent，套用時會加 `route -p`，重開機後仍保留。

### 檔案

| 檔案 | 說明 |
|------|------|
| `start_route.bat` | 啟動程式（自動 UAC） |
| `route_manager.py` | 主程式 |
| `route_config.json` | 設定檔（自動產生） |

---

## ProxyRouter (備選)

### 使用方式

1. 雙擊 `start_proxy.bat`
2. 選擇 **1** - 選擇熱點網卡
3. 選擇 **2** - 新增路由目標（格式 `IP:Port`，例如 `1.34.56.127:5000`）
4. 選擇 **5** - 啟動代理伺服器

### 設定瀏覽器 Proxy

**不要**設系統全域 Proxy，只在需要的瀏覽器設定，以免影響 Outlook/Teams：

- Firefox：設定 → 網路設定 → 手動設定 Proxy → `127.0.0.1:8888`
- Chrome / Edge：建議用 **SwitchyOmega** 等擴充套件，只對特定網址套用 Proxy

若要全域使用 Proxy 又不影響其他程式，請改用 PAC 檔：

```javascript
function FindProxyForURL(url, host) {
    if (host == "1.34.56.127") return "PROXY 127.0.0.1:8888";
    return "DIRECT";
}
```

### 檔案

| 檔案 | 說明 |
|------|------|
| `start_proxy.bat` | 啟動程式 |
| `proxy_router.py` | 主程式 |
| `proxy_config.json` | 設定檔（自動產生） |

---

## 注意事項

- 使用前請先連接熱點
- RouteManager 需以系統管理員身分執行
- VPN 連線時會覆寫路由表，套用後建議用選項 **7** 確認狀態
