# 企業管理系統（Python / PyQt6）

## 執行

```bash
pip install -r requirements.txt
python main.py
```

需安裝 [Microsoft Access Database Engine](https://www.microsoft.com/en-us/download/details.aspx?id=54920)（或已安裝 Office 含 Access ODBC）以連線 `.mdb` / `.accdb`。

## 檔案配置（與 `main.py` 同目錄）

| 檔案 | 說明 |
|------|------|
| `user_data.mdb`（或 `USER_DATA.mdb`） | 登入：`USERS`、`sys_co`、`SYS_GROUP` |
| `sys_data.mdb`（或 `SYS_DATA.mdb`） | `program`、`MAINMENU`、`columns` |
| `{公司編號}.MDB` | 營運資料表，例如 `GS.MDB` |

## 主要資料表欄位（建議）

- **USERS**：`USER_NO`, `PASSWORD`, `GROUP_NO`, `LAST_CO`
- **sys_co**：`CO_KEY`
- **SYS_GROUP**：`GROUP_NO`, `GROUP_LEVEL`（數字越大權限越高時，可執行 `program.LEVEL` 較小的程式；本程式規則為 `GROUP_LEVEL >= PROGRAM.LEVEL` 才顯示該程式）
- **program**：`PRG_GROUP`, `DO_PROC`, `WORK_FILE`, `TX_FILE`, `CHN_TITLE`, `ENG_TITLE`, `NEED_DO`, 選用 `ITEM_NO`, `LEVEL`
- **MAINMENU**：`MENU_TYPE`, `SEQ_NO`, `CHN_TITLE`, `ENG_TITLE`, `NEED_DO`（`MENU_TYPE` 對應 `program.PRG_GROUP`）
- **columns**：`DBF_NAME`, `NAME`, `CHN_TITLE`, `ENG_TITLE`；選用 **`GRID_VIEW`**、**`CTRL_EDIT`**、**`DATA_FORMAT`**（文字）。有 **`GRID_VIEW`** 欄時，主檔／TX 明細 Grid 僅顯示 `columns` 有定義且為真之欄位。有 **`CTRL_EDIT`** 欄時，輸入表單僅顯示並編輯 `columns` 有定義且為真之欄位。若無上述欄位，則行為同「顯示／編輯全部實體欄位」。**`DATA_FORMAT`** 非空白時，該欄 Grid 與輸入日期格式以此為準（Qt 日期格式，會將常見 `YYYY`/`DD` 轉成 `yyyy`/`dd`）；空白時日期欄仍用預設 `yyyy/MM/dd`。

若無 Access，可於選單「資料庫」改選 SQLite；登入仍須能讀取 `user_data.mdb`（或自行改為略過登入的測試模式）。

## 功能摘要

- Fusion 介面、6 種淡色主題、中英切換
- 五種主選單呈現 + 工具列快速切換
- 依權限篩選程式清單；`DO_PROC` 開啟 `WORK_FILE` 於右側分頁
- Grid：搜尋（Enter／按鈕定位）、過濾；雙擊／Enter 開「明細」分頁（含 TX_FILE 明細 Grid）
- 工具列：新增／更改／刪除／複製／列印預覽／離開
