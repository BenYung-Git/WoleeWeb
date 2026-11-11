"""AI_COMMAND：對話指令表（COLUMNS.DBF_NAME / PROGRAM / 實體表）與儲存。"""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.db_backend import AccessBackend, DbBackendBase, SQLiteBackend
from core.db_factory import get_backend_for_path, resolve_metadata_db_path

AI_COMMAND_DO_PROC = "AI_COMMAND"
AI_COMMAND_TABLE = "AI_COMMAND"
AI_COMMAND_WORK_DB = "USER_DATA.MDB"

# 實體欄位（與 COLUMNS.NAME 對應）
FIELD_CODE = "CMD_CODE"
FIELD_TITLE = "CMD_TITLE"
FIELD_PROMPT = "CMD_PROMPT"
FIELD_REPLY = "CMD_REPLY"
FIELD_CHAT = "CMD_CHAT"
FIELD_USER = "USER"
FIELD_DATE = "AI_DATE"
FIELD_DELETED = "DELETED"

_COLUMN_DEFS: List[Dict[str, Any]] = [
    {
        "NAME": FIELD_CODE,
        "CHN_TITLE": "指令 #",
        "ENG_TITLE": "Command #",
        "GRID_VIEW": True,
        "GRID_INDEX": 3,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 3,
        "DATA_TYPE": "S",
        "WIDTH": 12,
        "EDIT_TYPE": "K",
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_TITLE,
        "CHN_TITLE": "標題",
        "ENG_TITLE": "Title",
        "GRID_VIEW": True,
        "GRID_INDEX": 6,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 6,
        "DATA_TYPE": "S",
        "WIDTH": 40,
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_PROMPT,
        "CHN_TITLE": "提問",
        "ENG_TITLE": "Prompt",
        "GRID_VIEW": True,
        "GRID_INDEX": 9,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 9,
        "DATA_TYPE": "S",
        "WIDTH": 60,
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_REPLY,
        "CHN_TITLE": "回覆",
        "ENG_TITLE": "Reply",
        "GRID_VIEW": True,
        "GRID_INDEX": 12,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 12,
        "DATA_TYPE": "S",
        "WIDTH": 60,
        "TBL_LIST": False,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_CHAT,
        "CHN_TITLE": "完整對話",
        "ENG_TITLE": "Full chat",
        "GRID_VIEW": False,
        "GRID_INDEX": 15,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 15,
        "DATA_TYPE": "S",
        "WIDTH": 80,
        "TBL_LIST": False,
        "SEARCH": False,
    },
    {
        "NAME": FIELD_USER,
        "CHN_TITLE": "使用者",
        "ENG_TITLE": "User",
        "GRID_VIEW": True,
        "GRID_INDEX": 18,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 18,
        "DATA_TYPE": "S",
        "WIDTH": 12,
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_DATE,
        "CHN_TITLE": "日期時間",
        "ENG_TITLE": "Date/Time",
        "GRID_VIEW": True,
        "GRID_INDEX": 21,
        "CTRL_EDIT": True,
        "CTRL_INDEX": 21,
        "DATA_TYPE": "S",
        "WIDTH": 19,
        "TBL_LIST": True,
        "SEARCH": True,
    },
    {
        "NAME": FIELD_DELETED,
        "CHN_TITLE": "刪除",
        "ENG_TITLE": "Deleted",
        "GRID_VIEW": False,
        "GRID_INDEX": 99,
        "CTRL_EDIT": False,
        "CTRL_INDEX": 99,
        "DATA_TYPE": "S",
        "WIDTH": 1,
        "TBL_LIST": False,
        "SEARCH": False,
    },
]


def _has_table(backend: DbBackendBase, table_name: str) -> bool:
    try:
        return bool(backend.list_columns(table_name))
    except Exception:
        return False


def _exec_non_query(backend: DbBackendBase, sql: str, params: Optional[Sequence[Any]] = None) -> Tuple[bool, str]:
    """執行 DDL／非查詢 SQL（含 commit）。"""
    try:
        if isinstance(backend, SQLiteBackend):
            conn = backend._connect()  # noqa: SLF001
            try:
                cur = conn.cursor()
                if params:
                    cur.execute(sql, tuple(params))
                else:
                    cur.execute(sql)
                conn.commit()
            finally:
                conn.close()
            return True, ""
        if isinstance(backend, AccessBackend):
            with backend.operation() as conn:
                cur = conn.cursor()
                if params:
                    cur.execute(sql, list(params))
                else:
                    cur.execute(sql)
                try:
                    conn.commit()
                except Exception:
                    pass
            return True, ""
        # 其他後端：盡量用 fetch_rows_sql（部分實作可跑 DDL）
        backend.fetch_rows_sql(sql, params=params, limit=0)
        err = getattr(backend, "last_error", "") or ""
        return (not err), err
    except Exception as ex:
        return False, str(ex)


def _col_map(backend: DbBackendBase, table: str) -> Dict[str, str]:
    """大寫欄名 → 實際欄名。"""
    out: Dict[str, str] = {}
    for c in backend.list_columns(table) or []:
        if c:
            out[str(c).strip().upper()] = str(c)
    return out


def _pick(cmap: Dict[str, str], *names: str) -> Optional[str]:
    for n in names:
        hit = cmap.get(n.upper())
        if hit:
            return hit
    return None


def ensure_ai_command_table(data_backend: DbBackendBase) -> Tuple[bool, str]:
    """在 USER_DATA（或指定後端）建立 AI_COMMAND 實體表。"""
    if _has_table(data_backend, AI_COMMAND_TABLE):
        return True, ""
    if isinstance(data_backend, SQLiteBackend):
        sql = (
            f'CREATE TABLE IF NOT EXISTS "{AI_COMMAND_TABLE}" ('
            f'"{FIELD_CODE}" TEXT, '
            f'"{FIELD_TITLE}" TEXT, '
            f'"{FIELD_PROMPT}" TEXT, '
            f'"{FIELD_REPLY}" TEXT, '
            f'"{FIELD_CHAT}" TEXT, '
            f'"{FIELD_USER}" TEXT, '
            f'"{FIELD_DATE}" TEXT, '
            f'"{FIELD_DELETED}" TEXT'
            f")"
        )
    else:
        # Access：長文用 MEMO
        sql = (
            f"CREATE TABLE {AI_COMMAND_TABLE} ("
            f"{FIELD_CODE} VARCHAR(40), "
            f"{FIELD_TITLE} VARCHAR(120), "
            f"{FIELD_PROMPT} MEMO, "
            f"{FIELD_REPLY} MEMO, "
            f"{FIELD_CHAT} MEMO, "
            f"{FIELD_USER} VARCHAR(40), "
            f"{FIELD_DATE} VARCHAR(30), "
            f"{FIELD_DELETED} VARCHAR(1)"
            f")"
        )
    return _exec_non_query(data_backend, sql)


def ensure_ai_command_columns(sys_backend: DbBackendBase) -> Tuple[bool, str]:
    """寫入 sys_data.COLUMNS（DBF_NAME=AI_COMMAND）；已存在則略過。"""
    cmap = _col_map(sys_backend, "columns")
    if not cmap:
        return False, "找不到 COLUMNS 資料表。"
    dbf_col = _pick(cmap, "DBF_NAME")
    name_col = _pick(cmap, "NAME")
    if not dbf_col or not name_col:
        return False, "COLUMNS 缺少 DBF_NAME / NAME。"

    existing: set[str] = set()
    _c, rows = sys_backend.fetch_rows_sql(
        f"SELECT {name_col} FROM columns WHERE {dbf_col} = ?",
        params=[AI_COMMAND_TABLE],
        limit=500,
    )
    for r in rows or []:
        if r:
            existing.add(str(r[0] or "").strip().upper())

    # insert_one 接受字串；Access BIT 由 coerce 轉成 Yes/No
    bit_t, bit_f = ("1", "0")

    for defn in _COLUMN_DEFS:
        fname = str(defn["NAME"]).upper()
        if fname in existing:
            continue
        fields: List[str] = []
        values: List[str] = []

        def add(logical: str, value: Any, *aliases: str) -> None:
            col = _pick(cmap, logical, *aliases)
            if not col:
                return
            fields.append(col)
            if isinstance(value, bool):
                values.append(bit_t if value else bit_f)
            elif value is None:
                values.append("")
            else:
                values.append(str(value))

        add("DBF_NAME", AI_COMMAND_TABLE)
        add("NAME", defn["NAME"])
        add("CHN_TITLE", defn.get("CHN_TITLE") or "")
        add("ENG_TITLE", defn.get("ENG_TITLE") or "")
        add("SCHN_TITLE", defn.get("CHN_TITLE") or "")
        add("GRID_VIEW", bool(defn.get("GRID_VIEW")))
        add("GRID_INDEX", float(defn.get("GRID_INDEX") or 0))
        add("CTRL_EDIT", bool(defn.get("CTRL_EDIT")))
        add("CTRL_LABEL", True)
        add("CTRL_INDEX", float(defn.get("CTRL_INDEX") or 0))
        add("CTRL_TYPE", "TEXT")
        add("DATA_TYPE", defn.get("DATA_TYPE") or "S")
        add("WIDTH", float(defn.get("WIDTH") or 10))
        add("TBL_LIST", bool(defn.get("TBL_LIST")))
        add("LIST_SEQ", 0.0)
        add("FIELD_TOTAL", False)
        add("SEARCH", bool(defn.get("SEARCH")))
        if defn.get("EDIT_TYPE"):
            add("EDIT_TYPE", defn["EDIT_TYPE"])
        if not sys_backend.insert_one("columns", fields, values):
            return False, getattr(sys_backend, "last_error", "") or f"無法寫入 COLUMNS：{fname}"
    return True, ""


def ensure_ai_command_program(sys_backend: DbBackendBase) -> Tuple[bool, str]:
    """寫入 PROGRAM（DO_PROC=AI_COMMAND）若尚不存在；已存在則確保 Need_Do 為真。"""
    cmap = _col_map(sys_backend, "program")
    if not cmap:
        return False, "找不到 PROGRAM 資料表。"
    do_col = _pick(cmap, "DO_PROC")
    if not do_col:
        return False, "找不到 PROGRAM.DO_PROC。"
    need_col = _pick(cmap, "Need_Do", "NEED_DO")

    _c, rows = sys_backend.fetch_rows_sql(
        f"SELECT {do_col}"
        + (f", {need_col}" if need_col else "")
        + f" FROM program WHERE {do_col} = ?",
        params=[AI_COMMAND_DO_PROC],
        limit=5,
    )
    if rows:
        # 舊列若 Need_Do=False 會被選單載入略過，強制改為 True
        if need_col:
            need_raw = rows[0][1] if len(rows[0]) > 1 else None
            need_ok = str(need_raw or "").strip().lower() in (
                "1",
                "-1",
                "true",
                "yes",
                "y",
            )
            if not need_ok and isinstance(need_raw, (int, float)) and int(need_raw) != 0:
                need_ok = True
            if not need_ok:
                bit_t = "1"
                ok = sys_backend.update_one(
                    "program",
                    [need_col],
                    [bit_t],
                    [do_col],
                    [AI_COMMAND_DO_PROC],
                )
                if not ok:
                    return (
                        False,
                        getattr(sys_backend, "last_error", "")
                        or "無法更新 PROGRAM.Need_Do。",
                    )
        return True, ""

    fields: List[str] = []
    values: List[str] = []
    bit_t, bit_f = ("1", "0")

    def add(logical: str, value: Any, *aliases: str) -> None:
        col = _pick(cmap, logical, *aliases)
        if not col:
            return
        fields.append(col)
        if isinstance(value, bool):
            values.append(bit_t if value else bit_f)
        elif value is None:
            values.append("")
        else:
            values.append(str(value))

    add("PRG_GROUP", "UTL")
    add("ItemNumber", 90.0, "ITEMNUMBER")
    add("Proc_Name", AI_COMMAND_DO_PROC, "PROC_NAME")
    add("Level", 99.0)
    add("STD_PROC", True, "Std_Proc", "STD_PORC")
    add("DO_PROC", AI_COMMAND_DO_PROC)
    # Need_Do 必須為真，ProgramRepository 才會載入此作業
    add("Need_Do", True, "NEED_DO")
    add("NEED_ATTACH", False)
    add("NEED_OTHER", False)
    add("WORK_PROC", AI_COMMAND_TABLE)
    add("WORK_DB", AI_COMMAND_WORK_DB)
    add("WORK_FILE", AI_COMMAND_TABLE)
    add("KEY_CODE", FIELD_CODE)
    add("ENG_TITLE", "AI Commands")
    add("CHN_TITLE", "AI 指令")
    add("SCHN_TITLE", "AI 指令")
    add("Need_TxLog", False, "NEED_TXLOG")

    if not sys_backend.insert_one("program", fields, values):
        return False, getattr(sys_backend, "last_error", "") or "無法寫入 PROGRAM。"
    return True, ""


def resolve_ai_command_data_path(base_dir: str) -> str:
    path = resolve_metadata_db_path(base_dir, AI_COMMAND_WORK_DB)
    if not path:
        from core.auth import resolve_user_data_path

        path = resolve_user_data_path(base_dir)
    return path or ""


def ensure_ai_command_infra(base_dir: str, sys_mdb_path: str) -> Tuple[bool, str]:
    """
    確保 AI_COMMAND 實體表、COLUMNS、PROGRAM 就緒。
    回傳 (ok, error)。
    """
    from core.auth import enumerate_sys_data_paths

    data_path = resolve_ai_command_data_path(base_dir)
    if not data_path or not os.path.isfile(data_path):
        return False, f"找不到 USER_DATA：{data_path or '(empty)'}"

    data_be = get_backend_for_path(data_path)
    ok, err = ensure_ai_command_table(data_be)
    if not ok:
        return False, err or "無法建立 AI_COMMAND 資料表。"

    # Windows 上 ProgramRepository 可能優先讀 .mdb，AppRuntime 則可能用較新的 .sqlite；
    # 兩邊都寫入，避免 GRID 開不到 DO_PROC。
    sys_paths: List[str] = []
    seen: set[str] = set()
    for p in [sys_mdb_path, *enumerate_sys_data_paths(base_dir)]:
        ap = os.path.abspath(p or "")
        if not ap or not os.path.isfile(ap):
            continue
        key = os.path.normcase(ap)
        if key in seen:
            continue
        seen.add(key)
        sys_paths.append(ap)
    if not sys_paths:
        return False, f"找不到 SYS_DATA：{sys_mdb_path or '(empty)'}"

    last_err = ""
    any_ok = False
    for sp in sys_paths:
        sys_be = get_backend_for_path(sp)
        ok, err = ensure_ai_command_columns(sys_be)
        if not ok:
            last_err = err or f"無法寫入 COLUMNS（{os.path.basename(sp)}）。"
            continue
        ok, err = ensure_ai_command_program(sys_be)
        if not ok:
            last_err = err or f"無法寫入 PROGRAM（{os.path.basename(sp)}）。"
            continue
        any_ok = True
    if not any_ok:
        return False, last_err or "無法寫入 SYS_DATA。"
    return True, ""


def format_current_command(
    prompt: str,
    reply: str = "",
    *,
    chn: bool = True,
) -> Tuple[str, str, str, str]:
    """將目前指令轉成 (title, prompt, reply, chat_text)。"""
    prompt_s = (prompt or "").strip()
    reply_s = (reply or "").strip()
    you = "您" if chn else "You"
    title = prompt_s.replace("\n", " ").strip()
    if len(title) > 40:
        title = title[:40] + "…"
    if not title:
        title = "AI 指令" if chn else "AI command"
    lines: List[str] = []
    if prompt_s:
        lines.append(f"{you}: {prompt_s}")
    if reply_s:
        lines.append(f"AI: {reply_s}")
    return title, prompt_s, reply_s, "\n\n".join(lines)


def format_chat_transcript(messages: Sequence[Dict[str, str]], *, chn: bool = True) -> Tuple[str, str, str, str]:
    """
    將對話訊息轉成 (title, prompt, reply, chat_text)。
    預設只取「目前／最後一則」使用者指令（及對應回覆），非整段對話。
    """
    last_user = ""
    last_reply = ""
    for m in messages or []:
        role = str(m.get("role") or "").strip().lower()
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            last_user = content
            last_reply = ""
        elif role == "assistant":
            last_reply = content
    return format_current_command(last_user, last_reply, chn=chn)


def save_ai_command(
    base_dir: str,
    sys_mdb_path: str,
    *,
    user_no: str,
    messages: Sequence[Dict[str, str]] = (),
    prompt: str = "",
    reply: str = "",
    title: str = "",
    lang: str = "CHN",
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    儲存「目前指令」至 AI_COMMAND。
    優先使用 prompt（輸入框目前內容）；否則取 messages 最後一則使用者指令。
    """
    ok, err = ensure_ai_command_infra(base_dir, sys_mdb_path)
    if not ok:
        return None, err

    chn = str(lang or "").upper().startswith("C")
    cur_prompt = (prompt or "").strip()
    cur_reply = (reply or "").strip()
    if cur_prompt:
        auto_title, prompt_s, reply_s, chat = format_current_command(
            cur_prompt, cur_reply, chn=chn
        )
    else:
        auto_title, prompt_s, reply_s, chat = format_chat_transcript(messages, chn=chn)
    if not prompt_s and not chat:
        return None, "沒有可儲存的指令。" if chn else "No command to save."

    data_path = resolve_ai_command_data_path(base_dir)
    backend = get_backend_for_path(data_path)
    cmap = _col_map(backend, AI_COMMAND_TABLE)
    if not cmap:
        return None, "AI_COMMAND 資料表無法讀取。"

    code = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_title = (title or "").strip() or auto_title

    payload = {
        FIELD_CODE: code,
        FIELD_TITLE: final_title,
        FIELD_PROMPT: prompt_s,
        FIELD_REPLY: reply_s,
        FIELD_CHAT: chat,
        FIELD_USER: str(user_no or "").strip(),
        FIELD_DATE: when,
        FIELD_DELETED: "",
    }
    fields: List[str] = []
    values: List[str] = []
    for logical, val in payload.items():
        col = cmap.get(logical.upper())
        if col:
            fields.append(col)
            values.append(val)
    if not fields:
        return None, "AI_COMMAND 無可寫入欄位。"
    if not backend.insert_one(AI_COMMAND_TABLE, fields, values):
        return None, getattr(backend, "last_error", "") or "儲存失敗。"
    return {
        "cmd_code": code,
        "cmd_title": final_title,
        "ai_date": when,
        "do_proc": AI_COMMAND_DO_PROC,
    }, None
