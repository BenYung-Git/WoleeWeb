from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple, NamedTuple

from core.db_backend import DbBackendBase
from core.db_factory import get_backend_for_path
from core.display_format import normalize_data_type

LanguageCode = Literal["CHN", "ENG"]


@dataclass(frozen=True)
class ColumnTitle:
    dbf_name: str
    name: str
    chn_title: str
    eng_title: str
    grid_view: bool = True
    ctrl_edit: bool = True
    data_format: str = ""
    # columns.DATA_TYPE：N=數字、S=文字、D=日期、B=布林(Y/N)
    data_type: str = ""
    # 報表／清單（columns 選用欄位）
    tbl_list: bool = True
    list_seq: int = 0
    ctrl_index: int = 0
    grid_index: int = 0
    field_total: bool = False
    edit_tab: str = ""
    # ED=永不可改；AE=僅新增／複製可改
    edit_type: str = ""
    # Grid 欄寬（字元數），來自 columns.WIDTH；0 表示未設定，沿用程式預設上下限。
    grid_width_chars: int = 0
    need_attach: bool = False
    attach_path: str = ""
    attach_key: str = ""
    need_other: bool = False
    other_title: str = ""
    # Lookup（columns.LOOKUP_*）
    lookup_db: str = ""
    lookup_key: str = ""
    lookup_ret: str = ""
    # 搜尋／輸入回寫：SEARCH_RET 格式為「本表欄=LOOKUP欄」（可多組）
    search_ret: str = ""
    # COMBO_LIST：下拉選項（分號／直線／換行分隔）；CTRL_TYPE=COMBO 時亦用下拉
    combo_list: str = ""
    ctrl_type: str = ""

    def get_title(self, lang: LanguageCode) -> str:
        if lang == "CHN":
            return self.chn_title or self.eng_title or self.name
        return self.eng_title or self.chn_title or self.name

    def combo_choices(self) -> List[str]:
        """解析 COMBO_LIST 為選項清單（去空白、去重且保序）。"""
        return parse_combo_list(self.combo_list)

    def uses_combo_editor(self) -> bool:
        if self.combo_choices():
            return True
        return (self.ctrl_type or "").strip().upper() in ("COMBO", "COMBOBOX", "DROPDOWN")


def parse_combo_list(raw: str) -> List[str]:
    """COMBO_LIST 字串 → 選項；以 / 分隔（去空白、去重且保序）。"""
    text = str(raw or "").strip()
    if not text:
        return []
    parts: List[str] = []
    for chunk in text.split("/"):
        s = chunk.strip()
        if not s:
            continue
        if s not in parts:
            parts.append(s)
    return parts


class ReportColumnSpec(NamedTuple):
    """單一報表欄：實體欄名、顯示標題、是否尾端合計。"""

    physical_name: str
    display_title: str
    field_total: bool


@dataclass(frozen=True)
class WorkActionFlags:
    """作業頁額外功能按鈕（PROGRAM 或 columns 的 NEED_ATTACH / NEED_OTHER）。"""

    need_attach: bool = False
    attach_path: str = ""
    attach_key: str = ""
    need_other: bool = False
    other_title: str = ""


def merge_work_action_flags(*parts: WorkActionFlags) -> WorkActionFlags:
    """合併多來源旗標；路徑與標題取第一個非空白值。"""
    need_attach = False
    attach_path = ""
    attach_key = ""
    need_other = False
    other_title = ""
    for p in parts:
        if p.need_attach:
            need_attach = True
            if not attach_path and p.attach_path:
                attach_path = p.attach_path
            if not attach_key and p.attach_key:
                attach_key = p.attach_key
        if p.need_other:
            need_other = True
            if not other_title and p.other_title:
                other_title = p.other_title
    return WorkActionFlags(
        need_attach=need_attach,
        attach_path=attach_path,
        attach_key=attach_key,
        need_other=need_other,
        other_title=other_title,
    )


def program_work_action_flags(program_item) -> WorkActionFlags:
    """自 PROGRAM 列（DO_PROC）讀取之 NEED_ATTACH / NEED_OTHER 等。"""
    if program_item is None:
        return WorkActionFlags()
    return WorkActionFlags(
        need_attach=bool(getattr(program_item, "need_attach", False)),
        attach_path=(getattr(program_item, "attach_path", None) or "").strip(),
        attach_key=(getattr(program_item, "attach_key", None) or "").strip(),
        need_other=bool(getattr(program_item, "need_other", False)),
        other_title=(getattr(program_item, "other_title", None) or "").strip(),
    )


def resolve_work_action_flags(
    data_dict: "DataDictionary",
    table_name: str,
    do_proc: str,
    program_item=None,
) -> WorkActionFlags:
    """合併 columns（WORK_PROC / DO_PROC）與 PROGRAM 之作業按鈕設定。"""
    return resolve_work_actions_for_program(
        data_dict, table_name, do_proc, program_item
    )


def resolve_work_actions_for_program(
    data_dict: "DataDictionary",
    table_name: str,
    do_proc: str,
    menu_item=None,
    resolved_item=None,
    data_item=None,
) -> WorkActionFlags:
    """
    合併 columns（DBF_NAME = WORK_PROC / DO_PROC）與 PROGRAM 多列之作業按鈕設定。
    桌面與 Web 共用，確保 NEED_ATTACH / NEED_OTHER 來源一致。
    """
    return merge_work_action_flags(
        data_dict.work_action_flags(table_name, do_proc),
        program_work_action_flags(menu_item),
        program_work_action_flags(resolved_item),
        program_work_action_flags(data_item),
    )


class DataDictionary:
    """
    讀取同目錄 sys_data.mdb 的 columns 表，建立內部字典 (DBF_NAME, NAME) → 欄位定義。

    流程：
    1. 程式啟動：load() 開啟 sys_data.mdb 並偵測 columns 欄位結構（不載入全表）。
    2. 開啟作業：PROGRAM → WORK_PROC；set_rule_alias(WORK_FILE, WORK_PROC) 時
       SELECT … FROM columns WHERE DBF_NAME = WORK_PROC，載入 NAME、CHN_TITLE、
       ENG_TITLE、WIDTH、GRID_VIEW、GRID_INDEX、CTRL_EDIT、CTRL_INDEX 等。
    3. GRID_VIEW 為真：Grid 顯示，依 GRID_INDEX（無則 CTRL_INDEX）排序；欄寬依 WIDTH。
    4. CTRL_EDIT 為真：輸入介面可編輯，依 CTRL_INDEX 排序。
    """

    def __init__(self, mdb_path: str) -> None:
        self.mdb_path = mdb_path
        self._titles: Dict[Tuple[str, str], ColumnTitle] = {}
        self._dbf_alias_by_table: Dict[str, str] = {}
        self._has_ctrl_edit_column: bool = False
        self._has_grid_view_column: bool = False
        self._has_data_format_column: bool = False
        self._has_data_type_column: bool = False
        self._has_tbl_list_column: bool = False
        self._has_list_seq_column: bool = False
        self._has_ctrl_index_column: bool = False
        self._has_grid_index_column: bool = False
        self._has_field_total_column: bool = False
        self._has_edit_tab_column: bool = False
        self._has_edit_type_column: bool = False
        self._has_width_column: bool = False
        self._has_need_attach_column: bool = False
        self._has_attach_path_column: bool = False
        self._has_attach_key_column: bool = False
        self._has_need_other_column: bool = False
        self._has_other_title_column: bool = False
        self._has_lookup_db_column: bool = False
        self._has_lookup_key_column: bool = False
        self._has_lookup_ret_column: bool = False
        self._has_search_ret_column: bool = False
        self._schema_probed: bool = False

    @staticmethod
    def _bool_col(val) -> bool:
        """Access Yes=-1、SQLite 1、字串 TRUE/Y 皆視為真。"""
        if val is None:
            return False
        s = str(val).strip().upper()
        if s in ("TRUE", "T", "Y", "YES", "1", "-1"):
            return True
        if s in ("FALSE", "F", "N", "NO", "0"):
            return False
        try:
            return int(float(val)) != 0
        except (TypeError, ValueError):
            return bool(val)

    @staticmethod
    def _int_col(val) -> int:
        """解析 CTRL_INDEX／GRID_INDEX 等：相容 int、float、'3.0' 字串。"""
        if val is None:
            return 0
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _has_sql_result(backend: DbBackendBase, sql: str) -> bool:
        cols, _rows = backend.fetch_rows_sql(sql, limit=1)
        if cols:
            return True
        return not bool((getattr(backend, "last_error", "") or "").strip())

    def load(self) -> None:
        """啟動／重載 metadata：清空欄位字典並偵測 columns 表結構（不 SELECT 全表）。"""
        self._titles.clear()
        self._schema_probed = False
        self._probe_columns_schema()

    def load_columns_for_dbf(self, dbf_name: str) -> None:
        """
        依 columns.DBF_NAME（通常為 PROGRAM.WORK_PROC）載入該作業欄位定義。
        每次開啟作業應呼叫一次以取得最新設定。
        """
        key = (dbf_name or "").strip().upper()
        if not key or not os.path.exists(self.mdb_path):
            return
        if not self._schema_probed:
            self._probe_columns_schema()

        self._remove_titles_for_dbf(key)

        backend = get_backend_for_path(self.mdb_path)
        parts = self._select_column_parts()
        sql = f"SELECT {', '.join(parts)} FROM columns WHERE DBF_NAME = ?"
        _cols, rows = backend.fetch_rows_sql(sql, params=[key], limit=5000)
        for row in rows:
            col = self._parse_columns_row(row)
            if col is None:
                continue
            self._titles[(key, col.name.upper())] = col

    def reload_columns_for_table(self, table_name: str) -> None:
        """重載指定資料表對應之 columns.DBF_NAME（含 WORK_FILE→WORK_PROC 別名）。"""
        self.load_columns_for_dbf(self._resolve_dbf_name(table_name))

    def _probe_columns_schema(self) -> None:
        self._has_ctrl_edit_column = False
        self._has_grid_view_column = False
        self._has_data_format_column = False
        self._has_data_type_column = False
        self._has_tbl_list_column = False
        self._has_list_seq_column = False
        self._has_ctrl_index_column = False
        self._has_grid_index_column = False
        self._has_field_total_column = False
        self._has_edit_tab_column = False
        self._has_edit_type_column = False
        self._has_width_column = False
        self._has_need_attach_column = False
        self._has_attach_path_column = False
        self._has_attach_key_column = False
        self._has_need_other_column = False
        self._has_other_title_column = False
        self._has_lookup_db_column = False
        self._has_lookup_key_column = False
        self._has_lookup_ret_column = False
        self._has_search_ret_column = False
        self._has_combo_list_column = False
        self._has_ctrl_type_column = False
        self._schema_probed = False
        if not os.path.exists(self.mdb_path):
            self._schema_probed = True
            return

        backend = get_backend_for_path(self.mdb_path)
        self._has_ctrl_edit_column = self._has_sql_result(backend, "SELECT CTRL_EDIT FROM columns")
        self._has_grid_view_column = self._has_sql_result(backend, "SELECT GRID_VIEW FROM columns")
        self._has_data_format_column = self._has_sql_result(backend, "SELECT DATA_FORMAT FROM columns")
        self._has_data_type_column = self._has_sql_result(backend, "SELECT [DATA_TYPE] FROM columns")
        if not self._has_data_type_column:
            self._has_data_type_column = self._has_sql_result(backend, "SELECT DATA_TYPE FROM columns")
        for colname, attr in (
            ("TBL_LIST", "_has_tbl_list_column"),
            ("LIST_SEQ", "_has_list_seq_column"),
            ("CTRL_INDEX", "_has_ctrl_index_column"),
            ("GRID_INDEX", "_has_grid_index_column"),
            ("FIELD_TOTAL", "_has_field_total_column"),
            ("EDIT_TAB", "_has_edit_tab_column"),
            ("EDIT_TYPE", "_has_edit_type_column"),
            ("[WIDTH]", "_has_width_column"),
            ("NEED_ATTACH", "_has_need_attach_column"),
            ("ATTACH_PATH", "_has_attach_path_column"),
            ("ATTACH_KEY", "_has_attach_key_column"),
            ("NEED_OTHER", "_has_need_other_column"),
            ("OTHER_TITLE", "_has_other_title_column"),
            ("LOOKUP_DB", "_has_lookup_db_column"),
            ("LOOKUP_KEY", "_has_lookup_key_column"),
            ("LOOKUP_RET", "_has_lookup_ret_column"),
            ("SEARCH_RET", "_has_search_ret_column"),
            ("COMBO_LIST", "_has_combo_list_column"),
            ("CTRL_TYPE", "_has_ctrl_type_column"),
        ):
            setattr(self, attr, self._has_sql_result(backend, f"SELECT {colname} FROM columns"))
        self._schema_probed = True

    def _select_column_parts(self) -> List[str]:
        parts = ["DBF_NAME", "NAME", "CHN_TITLE", "ENG_TITLE"]
        if self._has_ctrl_edit_column:
            parts.append("CTRL_EDIT")
        if self._has_grid_view_column:
            parts.append("GRID_VIEW")
        if self._has_data_format_column:
            parts.append("DATA_FORMAT")
        if self._has_data_type_column:
            parts.append("[DATA_TYPE]")
        if self._has_tbl_list_column:
            parts.append("TBL_LIST")
        if self._has_list_seq_column:
            parts.append("LIST_SEQ")
        if self._has_ctrl_index_column:
            parts.append("CTRL_INDEX")
        if self._has_grid_index_column:
            parts.append("GRID_INDEX")
        if self._has_field_total_column:
            parts.append("FIELD_TOTAL")
        if self._has_edit_tab_column:
            parts.append("EDIT_TAB")
        if self._has_edit_type_column:
            parts.append("EDIT_TYPE")
        if self._has_width_column:
            parts.append("[WIDTH]")
        if self._has_need_attach_column:
            parts.append("NEED_ATTACH")
        if self._has_attach_path_column:
            parts.append("ATTACH_PATH")
        if self._has_attach_key_column:
            parts.append("ATTACH_KEY")
        if self._has_need_other_column:
            parts.append("NEED_OTHER")
        if self._has_other_title_column:
            parts.append("OTHER_TITLE")
        if self._has_lookup_db_column:
            parts.append("LOOKUP_DB")
        if self._has_lookup_key_column:
            parts.append("LOOKUP_KEY")
        if self._has_lookup_ret_column:
            parts.append("LOOKUP_RET")
        if self._has_search_ret_column:
            parts.append("SEARCH_RET")
        if self._has_combo_list_column:
            parts.append("COMBO_LIST")
        if self._has_ctrl_type_column:
            parts.append("CTRL_TYPE")
        return parts

    def _parse_columns_row(self, row) -> Optional[ColumnTitle]:
        if not row or len(row) < 4:
            return None
        dbf_name = str(row[0]).strip() if row[0] is not None else ""
        name = str(row[1]).strip() if row[1] is not None else ""
        if not name:
            return None
        chn_title = str(row[2]).strip() if row[2] is not None else ""
        eng_title = str(row[3]).strip() if row[3] is not None else ""
        i = 4
        ctrl_edit = True
        grid_view = True
        data_format = ""
        data_type = ""
        if self._has_ctrl_edit_column:
            ctrl_edit = self._bool_col(row[i])
            i += 1
        if self._has_grid_view_column:
            grid_view = self._bool_col(row[i])
            i += 1
        if self._has_data_format_column:
            data_format = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        if self._has_data_type_column:
            data_type = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        tbl_list = True
        list_seq = 0
        ctrl_index = 0
        grid_index = 0
        field_total = False
        edit_tab = ""
        edit_type = ""
        if self._has_tbl_list_column:
            tbl_list = self._bool_col(row[i])
            i += 1
        if self._has_list_seq_column:
            list_seq = self._int_col(row[i])
            i += 1
        if self._has_ctrl_index_column:
            ctrl_index = self._int_col(row[i])
            i += 1
        if self._has_grid_index_column:
            grid_index = self._int_col(row[i])
            i += 1
        if self._has_field_total_column:
            field_total = self._bool_col(row[i])
            i += 1
        if self._has_edit_tab_column:
            edit_tab = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        if self._has_edit_type_column:
            edit_type = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        grid_width_chars = 0
        if self._has_width_column:
            grid_width_chars = self._int_col(row[i])
            if grid_width_chars < 0:
                grid_width_chars = 0
            i += 1
        need_attach = False
        attach_path = ""
        attach_key = ""
        need_other = False
        other_title = ""
        if self._has_need_attach_column:
            need_attach = self._bool_col(row[i])
            i += 1
        if self._has_attach_path_column:
            attach_path = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        if self._has_attach_key_column:
            attach_key = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        if self._has_need_other_column:
            need_other = self._bool_col(row[i])
            i += 1
        if self._has_other_title_column:
            other_title = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        lookup_db = ""
        lookup_key = ""
        lookup_ret = ""
        if self._has_lookup_db_column:
            lookup_db = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        if self._has_lookup_key_column:
            lookup_key = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        if self._has_lookup_ret_column:
            lookup_ret = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        search_ret = ""
        if self._has_search_ret_column:
            search_ret = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        combo_list = ""
        if self._has_combo_list_column:
            combo_list = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        ctrl_type = ""
        if self._has_ctrl_type_column:
            ctrl_type = str(row[i]).strip() if row[i] is not None else ""
            i += 1
        return ColumnTitle(
            dbf_name=dbf_name,
            name=name,
            chn_title=chn_title,
            eng_title=eng_title,
            grid_view=grid_view,
            ctrl_edit=ctrl_edit,
            data_format=data_format,
            data_type=data_type,
            tbl_list=tbl_list,
            list_seq=list_seq,
            ctrl_index=ctrl_index,
            grid_index=grid_index,
            field_total=field_total,
            edit_tab=edit_tab,
            edit_type=edit_type,
            grid_width_chars=grid_width_chars,
            need_attach=need_attach,
            attach_path=attach_path,
            attach_key=attach_key,
            need_other=need_other,
            other_title=other_title,
            lookup_db=lookup_db,
            lookup_key=lookup_key,
            lookup_ret=lookup_ret,
            search_ret=search_ret,
            combo_list=combo_list,
            ctrl_type=ctrl_type,
        )

    def _remove_titles_for_dbf(self, dbf_key: str) -> None:
        drop = [k for k in self._titles if k[0] == dbf_key]
        for k in drop:
            del self._titles[k]

    def get_title(self, dbf_name: str, field_name: str, lang: LanguageCode) -> str:
        col = self._meta(dbf_name, field_name)
        if not col:
            return field_name
        return col.get_title(lang)

    def _has_titles_for_dbf(self, dbf_name: str) -> bool:
        key = (dbf_name or "").strip().upper()
        if not key:
            return False
        return any(k[0] == key for k in self._titles)

    def ensure_tx_column_rules(self, tx_table: str, work_proc: str) -> None:
        """
        TX_FILE 明細：優先使用 columns.DBF_NAME = 明細表名；
        僅在該表無任何定義時，才退回 WORK_PROC（WIDTH／GRID_VIEW 等）。
        """
        tx = (tx_table or "").strip().upper()
        proc = (work_proc or "").strip().upper()
        if not tx:
            return
        self.load_columns_for_dbf(tx)
        if self._has_titles_for_dbf(tx):
            self._dbf_alias_by_table.pop(tx, None)
        elif proc:
            self._dbf_alias_by_table[tx] = proc
        else:
            self._dbf_alias_by_table.pop(tx, None)

    def set_rule_alias(self, table_name: str, dbf_name: str) -> None:
        """
        指定資料表欄位規則來源（WORK_FILE → WORK_PROC）。
        執行 DO_PROC 時呼叫：連線 sys_data.mdb，SELECT columns WHERE DBF_NAME = WORK_PROC，
        載入 NAME、CHN_TITLE、ENG_TITLE、GRID_VIEW、GRID_INDEX、WIDTH、DATA_TYPE、
        DATA_FORMAT、NEED_ATTACH、ATTACH_PATH、ATTACH_KEY、NEED_OTHER、OTHER_TITLE、
        LOOKUP_DB、LOOKUP_KEY、LOOKUP_RET、SEARCH_RET 等至內部字典。
        """
        t = (table_name or "").strip().upper()
        d = (dbf_name or "").strip().upper()
        if not t:
            return
        if not d:
            self._dbf_alias_by_table.pop(t, None)
            return
        self._dbf_alias_by_table[t] = d
        self.load_columns_for_dbf(d)

    def resolve_rule_dbf_name(self, table_name: str) -> str:
        """WORK_FILE 等資料表對應之 columns.DBF_NAME（通常為 WORK_PROC）。"""
        return self._resolve_dbf_name(table_name)

    def _resolve_dbf_name(self, table_name: str) -> str:
        key = (table_name or "").strip().upper()
        return self._dbf_alias_by_table.get(key, key)

    def _column_rule_dbf(self, table_name: str) -> str:
        """
        Grid／輸入篩選用的 columns.DBF_NAME。
        若已載入該實體表名（如 TX 明細表）的定義，只用該表，避免誤用 WORK_PROC 主檔欄位。
        """
        t = (table_name or "").strip().upper()
        if t and self._has_titles_for_dbf(t):
            return t
        return self._resolve_dbf_name(table_name)

    def _meta_at_dbf(self, dbf_name: str, col: str) -> Optional[ColumnTitle]:
        return self._titles.get(((dbf_name or "").strip().upper(), col.upper()))

    def _meta(self, table_name: str, col: str) -> Optional[ColumnTitle]:
        t = (table_name or "").strip().upper()
        key = col.upper()
        direct = self._titles.get((t, key))
        if direct is not None:
            return direct
        alias = self._dbf_alias_by_table.get(t)
        if alias:
            return self._titles.get((alias.upper(), key))
        return None

    def get_data_format(self, dbf_name: str, field_name: str) -> str:
        col = self._meta(dbf_name, field_name)
        if not col:
            return ""
        return (col.data_format or "").strip()

    def get_data_type(self, dbf_name: str, field_name: str) -> str:
        col = self._meta(dbf_name, field_name)
        if not col:
            return ""
        return normalize_data_type(col.data_type or "")

    def get_edit_tab(self, dbf_name: str, field_name: str) -> str:
        col = self._meta(dbf_name, field_name)
        if not col:
            return ""
        return (col.edit_tab or "").strip()

    def get_edit_type(self, dbf_name: str, field_name: str) -> str:
        col = self._meta(dbf_name, field_name)
        if not col:
            return ""
        return (col.edit_type or "").strip().upper()

    def clear_values_for_copy(
        self,
        dbf_name: str,
        values: Dict[str, str],
        *,
        also_clear_fields: Optional[Sequence[str]] = None,
    ) -> Dict[str, str]:
        """
        複製單據時準備表單值：
        - EDIT_TYPE=ED 的欄位清空（如 TX_KEY／TX_NO／金額等）
        - 另可強制清空主鍵候選欄（相容未設 EDIT_TYPE 的表）
        """
        out = {k: ("" if v is None else str(v)) for k, v in (values or {}).items()}
        for name in list(out.keys()):
            if self.get_edit_type(dbf_name, name) == "ED":
                out[name] = ""
        extra: List[str] = []
        for c in also_clear_fields or ():
            s = str(c or "").strip()
            if s and s.upper() not in {x.upper() for x in extra}:
                extra.append(s)
        if extra:
            want = {x.upper() for x in extra}
            for name in list(out.keys()):
                if str(name or "").strip().upper() in want:
                    out[name] = ""
        return out

    def _work_action_flags_for_dbf(self, dbf_key: str) -> WorkActionFlags:
        """彙整單一 columns.DBF_NAME 下各欄之 NEED_ATTACH / NEED_OTHER。"""
        key = (dbf_key or "").strip().upper()
        if not key:
            return WorkActionFlags()
        if not self._has_titles_for_dbf(key):
            self.load_columns_for_dbf(key)
        need_attach = False
        attach_path = ""
        attach_key = ""
        need_other = False
        other_title = ""
        for (dbf, _name), col in self._titles.items():
            if dbf != key:
                continue
            if col.need_attach:
                need_attach = True
                if not attach_path and col.attach_path:
                    attach_path = col.attach_path
                if not attach_key and col.attach_key:
                    attach_key = col.attach_key
            if col.need_other:
                need_other = True
                if not other_title and col.other_title:
                    other_title = col.other_title
        return WorkActionFlags(
            need_attach=need_attach,
            attach_path=attach_path,
            attach_key=attach_key,
            need_other=need_other,
            other_title=other_title,
        )

    def work_action_flags(
        self, table_name: str, do_proc: str = ""
    ) -> WorkActionFlags:
        """
        彙整 columns 中 NEED_ATTACH / NEED_OTHER（WORK_PROC 與 DO_PROC）。
        任一欄為真即啟用；路徑與標題取第一個符合欄位之設定。
        """
        rule_dbf = self._column_rule_dbf(table_name)
        proc_key = (do_proc or "").strip().upper()
        dbf_keys: List[str] = []
        for k in (rule_dbf, proc_key):
            ku = (k or "").strip().upper()
            if ku and ku not in dbf_keys:
                dbf_keys.append(ku)
        merged = WorkActionFlags()
        for dbf in dbf_keys:
            merged = merge_work_action_flags(merged, self._work_action_flags_for_dbf(dbf))
        return merged

    def get_grid_width_chars(self, dbf_name: str, field_name: str) -> int:
        """columns.WIDTH：Grid 欄寬字元數；0 表示未設定或字典無此欄。"""
        col = self._meta(dbf_name, field_name)
        if not col:
            return 0
        try:
            n = int(col.grid_width_chars)
        except (TypeError, ValueError):
            return 0
        return max(0, n)

    def get_lookup(
        self, dbf_name: str, field_name: str
    ) -> Tuple[str, str, str]:
        """回傳 (LOOKUP_DB, LOOKUP_KEY, LOOKUP_RET)；無定義則空白。"""
        col = self._meta(dbf_name, field_name)
        if not col:
            return "", "", ""
        return (
            (col.lookup_db or "").strip(),
            (col.lookup_key or "").strip(),
            (col.lookup_ret or "").strip(),
        )

    def get_search_ret(self, dbf_name: str, field_name: str) -> str:
        col = self._meta(dbf_name, field_name)
        return (col.search_ret or "").strip() if col else ""

    def get_combo_list(self, dbf_name: str, field_name: str) -> str:
        col = self._meta(dbf_name, field_name)
        return (col.combo_list or "").strip() if col else ""

    def get_ctrl_type(self, dbf_name: str, field_name: str) -> str:
        col = self._meta(dbf_name, field_name)
        return (col.ctrl_type or "").strip() if col else ""

    def get_combo_choices(self, dbf_name: str, field_name: str) -> List[str]:
        col = self._meta(dbf_name, field_name)
        return col.combo_choices() if col else []

    def field_uses_combo(self, dbf_name: str, field_name: str) -> bool:
        col = self._meta(dbf_name, field_name)
        return bool(col and col.uses_combo_editor())

    def list_search_ret_rules(self, table_name: str) -> List[Dict[str, str]]:
        """
        列出有 SEARCH_RET＋LOOKUP_DB＋LOOKUP_KEY 的規則。
        每筆：source_field, lookup_db, lookup_key, lookup_ret, search_ret。
        """
        if not getattr(self, "_has_search_ret_column", False):
            return []
        rule_dbf = (self._column_rule_dbf(table_name) or "").strip().upper()
        if not rule_dbf:
            return []
        out: List[Dict[str, str]] = []
        seen: set = set()
        for (dbf_key, _uname), col in self._titles.items():
            if dbf_key != rule_dbf:
                continue
            search_ret = (col.search_ret or "").strip()
            lookup_db = (col.lookup_db or "").strip()
            lookup_key = (col.lookup_key or "").strip()
            if not search_ret or not lookup_db or not lookup_key:
                continue
            # 略過純布林旗標（舊資料）；須為可回存的欄位名
            if search_ret.upper() in {
                "Y",
                "N",
                "YES",
                "NO",
                "TRUE",
                "FALSE",
                "1",
                "0",
                "-1",
            }:
                continue
            sig = (lookup_db.upper(), lookup_key.upper(), search_ret.upper())
            if sig in seen:
                continue
            seen.add(sig)
            out.append(
                {
                    "source_field": col.name,
                    "lookup_db": lookup_db,
                    "lookup_key": lookup_key,
                    "lookup_ret": (col.lookup_ret or "").strip(),
                    "search_ret": search_ret,
                }
            )
        return out

    def search_physical_indices(
        self, table_name: str, physical: List[str]
    ) -> Optional[List[int]]:
        """
        相容舊呼叫：有 SEARCH_RET 規則時，回傳「=」左邊目標欄在 physical 的索引；
        否則 None（搜尋全部欄位）。
        """
        from core.search_ret_lookup import parse_search_ret_pairs

        rules = self.list_search_ret_rules(table_name)
        if not rules:
            return None
        indices: List[int] = []
        for rule in rules:
            for dest, _src in parse_search_ret_pairs(rule.get("search_ret") or ""):
                want = (dest or "").strip().upper()
                for i, name in enumerate(physical or []):
                    if (name or "").strip().upper() == want and i not in indices:
                        indices.append(i)
        return indices if indices else None

    def _index_sort_key(
        self, meta: ColumnTitle, physical_order: int, *, for_grid: bool
    ) -> int:
        if for_grid and self._has_grid_index_column:
            gi = meta.grid_index
            if gi > 0:
                return gi
        if self._has_ctrl_index_column:
            ci = meta.ctrl_index
            if ci > 0:
                return ci
        return physical_order + 1

    def _ordered_columns_with_flag(
        self,
        table_name: str,
        physical: List[str],
        *,
        flag_column_exists: bool,
        flag_predicate: Callable[[ColumnTitle], bool],
        for_grid: bool = False,
    ) -> List[str]:
        """
        依 columns 旗標篩選實體欄位並排序。
        Grid：GRID_INDEX（無則 CTRL_INDEX）；輸入：CTRL_INDEX。
        flag_column_exists 為 False 時回傳全部 physical（維持原順序）。
        """
        if not physical:
            return []
        if not flag_column_exists:
            return list(physical)
        rule_dbf = self._column_rule_dbf(table_name)
        selected: List[Tuple[str, int, int]] = []
        for i, c in enumerate(physical):
            m = self._meta_at_dbf(rule_dbf, c)
            if m is not None and flag_predicate(m):
                selected.append(
                    (c, self._index_sort_key(m, i, for_grid=for_grid), i)
                )
        out = [name for name, _idx, _i in sorted(selected, key=lambda x: (x[1], x[2]))]
        # 有 GRID_VIEW 定義但 physical 與 columns 對不上時，仍顯示全部實體欄位
        if flag_column_exists and not out and physical:
            return list(physical)
        return out

    def grid_columns_for_table(self, table_name: str, physical: List[str]) -> List[str]:
        """
        若 columns 有 GRID_VIEW：僅顯示定義且 GRID_VIEW 為真之欄，依 GRID_INDEX 排序。
        若無 GRID_INDEX 欄則改依 CTRL_INDEX；皆無則維持原實體欄順序。
        若無 GRID_VIEW 欄：回傳全部實體欄位（原順序）。
        """
        return self._ordered_columns_with_flag(
            table_name,
            physical,
            flag_column_exists=self._has_grid_view_column,
            flag_predicate=lambda m: m.grid_view,
            for_grid=True,
        )

    def edit_columns_for_table(self, table_name: str, physical: List[str]) -> List[str]:
        """
        若 columns 有 CTRL_EDIT：僅在輸入介面顯示可編輯且 CTRL_EDIT 為真之欄，依 CTRL_INDEX 排序。
        若無 CTRL_EDIT 欄：回傳全部實體欄位（原順序）。
        """
        return self._ordered_columns_with_flag(
            table_name,
            physical,
            flag_column_exists=self._has_ctrl_edit_column,
            flag_predicate=lambda m: m.ctrl_edit,
            for_grid=False,
        )

    def grid_display_projection(self, table_name: str, physical: List[str]) -> Tuple[List[str], List[int]]:
        """Grid 顯示欄名與對應實體列索引，供 TX 明細等對應 SELECT * 結果。"""
        if not physical:
            return [], []
        disp = self.grid_columns_for_table(table_name, physical)
        idxs = [physical.index(c) for c in disp]
        return disp, idxs

    def report_column_specs(
        self, table_name: str, physical: List[str], lang: LanguageCode
    ) -> List[ReportColumnSpec]:
        """
        依 columns（DBF_NAME=資料表）：TBL_LIST 為真者列入報表；
        排序：LIST_SEQ（非 0 優先），否則 CTRL_INDEX；皆無則維持原 physical 順序作 ctrl 序。
        """
        if not physical:
            return []
        tkey = self._resolve_dbf_name(table_name)
        candidates: List[Tuple[Tuple[int, ...], ColumnTitle]] = []
        for order_i, pname in enumerate(physical):
            col = self._titles.get((tkey, pname.upper()))
            if col is None:
                continue
            if self._has_tbl_list_column and not col.tbl_list:
                continue
            ci = col.ctrl_index if self._has_ctrl_index_column else order_i
            if self._has_list_seq_column:
                if col.list_seq != 0:
                    sk = (0, col.list_seq, ci, order_i)
                else:
                    sk = (1, ci, order_i)
            else:
                sk = (0, ci, order_i)
            candidates.append((sk, col))
        candidates.sort(key=lambda x: x[0])
        out: List[ReportColumnSpec] = []
        for _sk, col in candidates:
            title = col.get_title(lang)
            out.append(
                ReportColumnSpec(
                    physical_name=col.name,
                    display_title=title,
                    field_total=col.field_total,
                )
            )
        return out

