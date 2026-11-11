"""主選單程式圖示鍵名 — 與 ui/main_window._menu_item_icon 邏輯一致（無 Qt 依賴）。"""
from __future__ import annotations


def resolve_menu_item_icon_key(do_proc: str, title: str) -> str:
    """
    依 DO_PROC / 標題決定語意分類，回傳 Web ui-icons.js 可解析的圖示鍵名。
    """
    proc = (do_proc or "").strip().upper()
    key = f"{proc} {title}".lower()
    icon_name = "applications-system"

    do_proc_icon_map = {
        "USERS": "system-users",
        "USER": "system-users",
        "SYS_USER": "system-users",
        "SYS_GROUP": "dialog-password",
        "GROUP": "dialog-password",
        "SYS_CO": "office-building",
        "COMPANY": "office-building",
        "ITEM": "package",
        "STOCK": "package",
        "INVENTORY": "package",
        "PURCHASE": "basket",
        "PO": "basket",
        "SALE": "view-pim-tasks",
        "SO": "view-pim-tasks",
        "REPORT": "x-office-document",
        "PRINT": "x-office-document",
        "ACCOUNT": "x-office-spreadsheet",
        "FINANCE": "x-office-spreadsheet",
        "SETTING": "preferences-system",
        "CONFIG": "preferences-system",
        "DATA": "server-database",
        "DB": "server-database",
    }
    if proc in do_proc_icon_map:
        icon_name = do_proc_icon_map[proc]
    else:
        prefix_rules = [
            (("USR", "USER"), "system-users"),
            (("GRP", "GROUP"), "dialog-password"),
            (("CO", "COMPANY"), "office-building"),
            (("ITEM", "INV", "STK"), "package"),
            (("PO", "PUR"), "basket"),
            (("SO", "SAL"), "view-pim-tasks"),
            (("RPT", "REP", "PRN"), "x-office-document"),
            (("ACC", "FIN"), "x-office-spreadsheet"),
            (("SET", "CFG"), "preferences-system"),
            (("DB", "DATA"), "server-database"),
        ]
        for prefixes, name in prefix_rules:
            if any(proc.startswith(p) for p in prefixes):
                icon_name = name
                break

    if icon_name == "applications-system":
        rules = [
            (("user", "users", "帳", "員工", "person", "member"), "system-users"),
            (("group", "權限", "role", "permission"), "dialog-password"),
            (("co", "company", "公司"), "office-building"),
            (("stock", "inventory", "item", "product", "品號", "料號"), "package"),
            (("sale", "order", "訂單", "銷"), "view-pim-tasks"),
            (("purchase", "採購"), "basket"),
            (("finance", "account", "會計", "帳務"), "x-office-spreadsheet"),
            (("report", "報表", "print"), "x-office-document"),
            (("setting", "config", "參數", "設定"), "preferences-system"),
            (("db", "data", "資料"), "server-database"),
        ]
        for keys, name in rules:
            if any(k in key for k in keys):
                icon_name = name
                break

    return icon_name
