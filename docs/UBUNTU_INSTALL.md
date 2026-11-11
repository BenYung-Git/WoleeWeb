# Ubuntu 重新安裝指南

不需從 Windows **逐檔同步**。請將 **整個 `WoleeWeb` 資料夾**（含程式與資料庫）一次性複製到 Ubuntu，再執行安裝腳本。

## 1. 複製專案（擇一）

### 方式 A：整個資料夾 SCP（在 Windows PowerShell）

```powershell
scp -r S:\WoleeWeb raymond@UbuntuServer:~/
```

### 方式 B：壓縮後傳輸

Windows 壓縮 `WoleeWeb` 為 zip，傳到 Ubuntu 後：

```bash
cd ~
unzip WoleeWeb.zip
# 或 tar -xzf WoleeWeb.tar.gz
```

### 必須包含的檔案

| 類型 | 檔案 |
|------|------|
| 程式 | 整個目錄（`api/`、`web/`、`core/`、`services/`、`launcher.py` 等） |
| 系統庫 | `sys_data.sqlite` 或 `sys_data.mdb` |
| 登入庫 | `user_data.sqlite` 或 `user_data.mdb` |
| 公司資料 | `GS.MDB` / `GS.sqlite` 等（依公司別） |

> **不要**只複製部分檔案；**不要**從 Windows 複製 `.venv`（會壞掉，須在 Ubuntu 重建）。

## 2. 重新安裝

**建議（Samba / Windows 共用目錄請用 Python 腳本，不受 CRLF 影響）：**

```bash
cd ~/WoleeWeb
python3 scripts/install_ubuntu.py
```

### Samba 共用目錄（例如 `/srv/samba/public/Share/WoleeWeb`）

專案放在 Windows/Samba 共用時，**不要在共用目錄建立 `.venv`**（權限常導致 `Permission denied`）。
請把 Python 套件裝在本機家目錄：

```bash
cd /srv/samba/public/Share/WoleeWeb
python3 scripts/install_ubuntu.py --venv-dir ~/.wolee-venv
source ~/.wolee-venv/bin/activate
python3 launcher.py --mode web --headless --host 0.0.0.0 --port 8080
```

若舊的 `.venv` 刪不掉，可略過刪除、直接改用 `--venv-dir`（不必先清掉共用目錄上的 `.venv`）。

### 登入庫 `user_data.sqlite` 唯讀

Samba 上 `user_data.sqlite` 常無法寫入，登入時會出現：

`更新登入資訊失敗：attempt to write a readonly database`

**自動處理（新版程式）**：若共用目錄內的 `user_data.sqlite` 唯讀，系統會複製到
`~/.wolee-local/WoleeWeb/user_data.sqlite` 並從該可寫副本更新 `LAST_CO`／`LOGIN_TIMES`。

**手動指定**（可選）：

```bash
mkdir -p ~/.wolee-local
cp /srv/samba/public/Share/WoleeWeb/user_data.sqlite ~/.wolee-local/
export WOLEE_USER_DATA_PATH=~/.wolee-local/user_data.sqlite
```

或請系統管理員將 Samba 共用改為可寫，並確認 `user_data.sqlite` 與目錄權限：

```bash
ls -la /srv/samba/public/Share/WoleeWeb/user_data.sqlite
touch /srv/samba/public/Share/WoleeWeb/user_data.sqlite
```

若 `touch` 失敗，表示共用仍為唯讀，請用上述本機副本方式。

或使用 shell 腳本（須先轉換換行）：

```bash
sed -i 's/\r$//' scripts/install_ubuntu.sh
bash scripts/install_ubuntu.sh
```

僅升級套件、保留既有 venv：

```bash
./scripts/install_ubuntu.sh --keep-venv
```

## 3. 啟動 Web

```bash
cd ~/WoleeWeb
source .venv/bin/activate
python3 launcher.py --mode web --headless --host 0.0.0.0 --port 8080
```

瀏覽器：`http://<Ubuntu的IP>:8080`

## 4. 驗證附件／其他按鈕

安裝腳本會檢查 `app.js`、`api/server.py` 與 `sys_data` 旗標。

手動檢查：

```bash
grep -c findMenuWorkActions web/static/app.js
grep app.js web/static/index.html
python3 scripts/debug_work_actions.py
```

開啟 **Purchase** 或 **Arap**，應看到 **附件** 與 **Payment/付款** 等按鈕。

## 5. 附件目錄（Q:\\ / S:\\docBiz\\Attachment\\...）

桌面版附件常在 Windows 的 `Q:\docBiz\Attachment\PURCHASE` 或 `S:\docBiz\Attachment\PURCHASE` 等路徑。Ubuntu Web **無法直接讀磁碟代號**，須：

### 5.1 掛載 Windows 共用目錄

```bash
sudo mkdir -p /srv/docBiz
sudo mount -t cifs //<Windows主機IP>/docBiz /srv/docBiz -o username=...,password=...,uid=raymond,gid=raymond
```

（實際 UNC 路徑請依貴公司檔案伺服器調整。）

### 5.2 設定路徑對應

複製範例並修改：

```bash
cd ~/WoleeWeb
cp attachment_path_map.json.example attachment_path_map.json
# 編輯 to 為實際掛載點，例如 /srv/docBiz
```

或使用環境變數：

```bash
export WOLEE_ATTACH_MAP='Q:\docBiz=/srv/docBiz;S:\docBiz=/srv/docBiz'
python3 launcher.py --mode web --headless --host 0.0.0.0 --port 8080
```

`PROGRAM.ATTACH_PATH` 可維持 `Q:\...` 或 `S:\...`；只要對應表有 `...\docBiz`，系統會自動對應到 Linux 掛載點（不同磁碟代號但相同相對路徑亦可）。

驗證：

```bash
ls /srv/docBiz/Attachment/PURCHASE/*GS-000092* 2>/dev/null
# 或（若對應 to 為 /srv/docBiz/docBiz）
ls /srv/docBiz/docBiz/Attachment/PURCHASE/SH-267078.pdf 2>/dev/null
```

## 6. 常見問題

| 問題 | 處理 |
|------|------|
| `python` 找不到 | 使用 `python3` |
| `.venv` 從 Windows 複製後壞掉 | 刪除 `.venv` 後重跑 `install_ubuntu.sh` |
| 按鈕仍無 | 確認 `app.js?v=35`、強制重新整理、重新登入 |
| 外機連不上 | `sudo ufw allow 8080/tcp` 或關閉防火牆測試 |
| `readonly database` 登入失敗 | 見上文「登入庫 user_data.sqlite 唯讀」；重啟 Web 後再登入 |
