# RouteManager

讓特定 IP 透過指定網卡（如行動熱點）連線，其餘流量維持走預設網卡。

透過 OS 層級路由表直接分流，不使用 Proxy，Outlook / Teams / OneDrive 等程式完全不受影響。

---

## 支援平台

| 平台 | 權限需求 | 路由指令 |
|------|---------|---------|
| Windows | 系統管理員 | `route add/delete` |
| macOS | sudo (root) | `route add/delete -host` |
| Linux | sudo (root) | `ip route add/del` |

---

## 使用方式

### Windows

1. 雙擊 `start_route.bat`（會自動請求系統管理員權限）
2. 選擇 **1** - 選擇熱點網卡
3. 選擇 **2** - 新增要走熱點的 IP（例如 `1.34.56.127`）
4. 選擇 **5** - 套用路由

### macOS / Linux

```bash
sudo python3 route_manager.py
```

或使用打包好的執行檔：

```bash
sudo ./RouteManager
```

---

## 功能選單

```
Options:
  1. Select hotspot adapter      # 選擇熱點網卡
  2. Add IP to route via hotspot # 新增 IP 路由
  3. Remove IP                   # 移除 IP
  4. Toggle persistent mode      # 切換持久模式
  5. Apply all routes NOW        # 立即套用所有路由
  6. Clear all routes NOW        # 清除所有路由
  7. Show current routing status # 顯示目前路由狀態
  8. Test route (tracert)        # 測試路由
  0. Exit                        # 離開
```

---

## 清除路由

- 選擇 **6** 手動清除
- 直接重開機（預設為 session only，非持久）

---

## 持久模式

選擇 **4** 切換成 Persistent：

| 平台 | 行為 |
|------|------|
| Windows | 套用時加 `route -p`，重開機後保留 |
| macOS | 需手動設定 launchd plist |
| Linux | 需手動設定 `/etc/network/interfaces` 或 netplan |

---

## 打包執行檔

使用 PyInstaller 打包成獨立執行檔：

```bash
python3 build.py
```

產出位置：`dist/RouteManager`（Windows 為 `dist/RouteManager.exe`）

**注意**：需在目標平台上執行打包，PyInstaller 無法跨平台編譯。

---

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `route_manager.py` | 主程式 |
| `route_config.json` | 設定檔（自動產生） |
| `start_route.bat` | Windows 啟動腳本（自動 UAC） |
| `build.py` | PyInstaller 打包腳本 |

---

## 注意事項

- 使用前請先連接熱點
- 路由表僅支援 IP 位址，不支援 Port 分流
- VPN 連線時可能覆寫路由表，套用後建議用選項 **7** 確認狀態
