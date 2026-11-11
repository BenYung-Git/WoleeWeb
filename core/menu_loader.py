from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Set, Tuple

from core.auth import parse_level_value
from core.db_backend import DbBackendBase
from core.db_factory import get_backend_for_path


LanguageCode = Literal["CHN", "ENG"]


@dataclass
class ProgramItem:
    group: str  # PRG_GROUP
    do_proc: str
    work_file: Optional[str]  # 主資料表
    tx_file: Optional[str]  # 交易詳細資料表
    chn_title: str
    eng_title: str
    need_do: bool
    order_no: int
    required_level: Optional[int] = None  # PROGRAM.LEVEL：可執行之最高(數值)群組等級（數字愈小權限愈高）
    proc_name: Optional[str] = None  # PROGRAM.PROC_NAME，與 SYS_DATA.REPORT.PROC_NAME 比對；空則列印時沿用 DO_PROC
    key_code: Optional[str] = None  # PROGRAM.KEY_CODE：主檔 WORK_FILE 上「由/至編號」對應之實體欄名（如 CUST_KEY）
    num_type: Optional[str] = None  # PROGRAM.NUM_TYPE：編號組別欄（如 TX_TYPE）
    num_control: Optional[str] = None  # PROGRAM.NUM_CONTROL：流水號欄（如 TX_NO）；與 NUM_TYPE 皆空則開新增編號介面
    num_digit: int = 8  # PROGRAM.NUM_DIGIT：流水號位數（前置補零）
    num_separate: Optional[str] = None  # PROGRAM.NUM_SEPARATE：組別與流水號分隔（如 -）→ TX_KEY=TX_TYPE+NUM_SEPARATE+TX_NO
    work_db: Optional[str] = None  # PROGRAM.WORK_DB：指定開啟資料庫（優先）
    co_key: Optional[str] = None  # PROGRAM.PRG_CO / CO_KEY：公司資料庫鍵或 GS/LCK/WLS 清單
    work_proc: Optional[str] = None  # PROGRAM.WORK_PROC：欄位規則來源之程式代號
    need_attach: bool = False  # PROGRAM.NEED_ATTACH：顯示附件按鈕
    attach_path: Optional[str] = None  # PROGRAM.ATTACH_PATH：附件目錄樣板
    attach_key: Optional[str] = None  # PROGRAM.ATTACH_KEY：附件比對欄位；空白則用 KEY_CODE
    need_other: bool = False  # PROGRAM.NEED_OTHER：顯示其他功能按鈕
    other_title: Optional[str] = None  # PROGRAM.OTHER_TITLE：其他功能按鈕標題
    std_proc: bool = True  # PROGRAM.STD_PROC（或舊欄 STD_PORC）：True=標準 Grid 作業

    def get_title(self, lang: LanguageCode) -> str:
        if lang == "CHN":
            return self.chn_title or self.eng_title or self.do_proc
        return self.eng_title or self.chn_title or self.do_proc


@dataclass
class ProgramBinding:
    """開啟作業時解析結果：選單列（如 DO_USER）與實際資料來源列（WORK_PROC 對應列）。"""

    menu_item: Optional[ProgramItem]
    data_item: Optional[ProgramItem]
    work_file: str
    rule_proc: str


@dataclass
class MainMenuGroup:
    """
    代表 MAINMENU + program 的一個功能群組：
    - menu_type: MAINMENU.MENU_TYPE
    - seq_no:    MAINMENU.SEQ_NO (主選單顯示順序)
    - chn_title / eng_title: 該群組在主選單上的顯示名稱
    - items:     底下所有 program.PRG_GROUP 對應的 ProgramItem 清單
    """

    menu_type: str
    seq_no: int
    chn_title: str
    eng_title: str
    need_do: bool
    items: List[ProgramItem]

    def get_title(self, lang: LanguageCode) -> str:
        if lang == "CHN":
            return self.chn_title or self.eng_title or self.menu_type
        return self.eng_title or self.chn_title or self.menu_type


class ProgramRepository:
    """
    登入後自同目錄 sys_data（.mdb／.sqlite）建立主選單。

    流程：
    1. 自動開啟同目錄 sys_data 資料庫
    2. 讀 MAINMENU：MENU_TYPE、SEQ_NO、CHN_TITLE、ENG_TITLE、NEED_DO
       （NEED_DO=FALSE 略過）
    3. 讀 program：PRG_GROUP、DO_PROC、CHN_TITLE、ENG_TITLE、STD_PROC／STD_PORC、
       NEED_DO、NUM_CONTROL、NUM_TYPE、NUM_SEPARATE、NUM_DIGIT、WORK_DB、
       WORK_FILE、TX_FILE 等（NEED_DO=FALSE 略過）
    4. MAINMENU.MENU_TYPE 對應 program.PRG_GROUP；程式項依 PRG_GROUP、ITEM_NO／ItemNumber 排序
    5. 結果存入內部字典／群組；再依登入者 LEVEL／公司篩選可用功能
    """

    def __init__(self, mdb_path: str) -> None:
        self.mdb_path = mdb_path
        self._items: List[ProgramItem] = []
        self._all_items: List[ProgramItem] = []
        # KEY: PRG_GROUP → List[ProgramItem]
        self._groups: Dict[str, List[ProgramItem]] = {}
        # KEY: DO_PROC（大寫）→ ProgramItem（內部字典）
        self._by_do_proc: Dict[str, ProgramItem] = {}
        # MAINMENU 資料：依 SEQ_NO 排序好的群組
        self._mainmenu_groups: List[MainMenuGroup] = []

    @staticmethod
    def _bool_flag(val: object) -> bool:
        """Access Yes=-1、SQLite 1、字串 TRUE/Y 皆視為真。"""
        if val is None:
            return False
        s = str(val).strip().upper()
        if s in ("TRUE", "T", "Y", "YES", "1", "-1"):
            return True
        if s in ("FALSE", "F", "N", "NO", "0"):
            return False
        try:
            return int(val) != 0  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return bool(val)

    @staticmethod
    def _has_query_columns(backend: DbBackendBase, sql: str) -> bool:
        cols, _rows = backend.fetch_rows_sql(sql, limit=1)
        if cols:
            return True
        return not bool((getattr(backend, "last_error", "") or "").strip())

    @staticmethod
    def _pick_table_column(backend: DbBackendBase, table_name: str, *candidates: str) -> Optional[str]:
        """依候選名稱（不分大小寫）解析實體欄位名。"""
        cols = backend.list_columns(table_name)
        by_upper = {(c or "").strip().upper(): c for c in cols if c}
        for name in candidates:
            hit = by_upper.get((name or "").strip().upper())
            if hit:
                return hit
        return None

    @staticmethod
    def _q_col(name: str) -> str:
        """SQL 欄位引號（Access []、SQLite \"\"）。"""
        n = (name or "").strip()
        if not n:
            return '""'
        return f'"{n.replace(chr(34), chr(34) * 2)}"'

    def _column_map_by_do(
        self,
        backend: DbBackendBase,
        col_do_proc: str,
        col_value: Optional[str],
        *,
        as_bool: bool = False,
        as_int: bool = False,
        default_bool: bool = False,
        default_int: int = 8,
    ) -> Dict[str, object]:
        """SELECT DO_PROC, col → {DO_PROC大寫: 值}。"""
        out: Dict[str, object] = {}
        if not col_value or not col_do_proc:
            return out
        _cols, rows = backend.fetch_rows_sql(
            f"SELECT {self._q_col(col_do_proc)}, {self._q_col(col_value)} FROM program",
            limit=5000,
        )
        for kr in rows:
            dp = str(kr[0]).strip() if kr and kr[0] is not None else ""
            if not dp:
                continue
            key = dp.upper()
            raw = kr[1] if len(kr) > 1 else None
            if as_bool:
                out[key] = self._bool_flag(raw if raw is not None else default_bool)
            elif as_int:
                try:
                    d = int(float(raw)) if raw is not None else default_int
                except (TypeError, ValueError):
                    d = default_int
                out[key] = max(1, d)
            else:
                out[key] = str(raw).strip() if raw is not None else ""
        return out

    def _rebuild_by_do_proc(self) -> None:
        self._by_do_proc = {
            p.do_proc.strip().upper(): p
            for p in self._items
            if (p.do_proc or "").strip()
        }

    @property
    def items(self) -> List[ProgramItem]:
        return list(self._items)

    @property
    def program_by_do_proc(self) -> Dict[str, ProgramItem]:
        """內部字典：DO_PROC（大寫）→ ProgramItem（已通過 NEED_DO／權限篩選）。"""
        return dict(self._by_do_proc)

    @property
    def grouped_items(self) -> Dict[str, List[ProgramItem]]:
        """
        仍保留原本介面：依 PRG_GROUP 回傳 ProgramItem 清單（僅受 program.NEED_DO 控制）。
        """
        return {k: list(v) for k, v in self._groups.items()}

    @property
    def mainmenu_groups(self) -> List[MainMenuGroup]:
        """
        依 MAINMENU.SEQ_NO + program.ITEM_NO／ItemNumber 整理好的主選單群組。
        僅包含 MAINMENU.NEED_DO 為 True 且底下仍有至少一個 ProgramItem 的群組。
        """
        return list(self._mainmenu_groups)

    def _items_for_menu_type(self, menu_type: str) -> List[ProgramItem]:
        """MAINMENU.MENU_TYPE 對應 program.PRG_GROUP（大小寫不敏感、去空白）。"""
        key = (menu_type or "").strip()
        if not key:
            return []
        if key in self._groups:
            return list(self._groups[key])
        upper = key.upper()
        for grp_key, items in self._groups.items():
            if (grp_key or "").strip().upper() == upper:
                return list(items)
        return []

    def _append_mainmenu_from_prg_groups(self) -> None:
        """無 MAINMENU 或無法對應時：依 PRG_GROUP 建立群組。"""
        for idx, (grp, items) in enumerate(
            sorted(self._groups.items(), key=lambda kv: kv[0])
        ):
            if not items:
                continue
            self._mainmenu_groups.append(
                MainMenuGroup(
                    menu_type=grp,
                    seq_no=idx,
                    chn_title=grp,
                    eng_title=grp,
                    need_do=True,
                    items=list(items),
                )
            )

    def load(self) -> None:
        from core.auth import enumerate_sys_data_paths, resolve_sys_data_path

        base_dir = os.path.dirname(os.path.abspath(self.mdb_path or "."))
        # 與 resolve_sys_data_path 一致：Windows 取較新檔（sqlite 常含 NUM_TYPE/NUM_CONTROL）
        preferred = ""
        if self.mdb_path and os.path.isfile(self.mdb_path):
            preferred = os.path.abspath(self.mdb_path)
        else:
            preferred = resolve_sys_data_path(base_dir)
        candidates: List[str] = []
        seen: Set[str] = set()
        for path in [preferred, *enumerate_sys_data_paths(base_dir)]:
            if not path:
                continue
            full = os.path.abspath(path)
            key = os.path.normcase(full)
            if key in seen or not os.path.isfile(full):
                continue
            seen.add(key)
            candidates.append(full)
        if not candidates:
            candidates = [resolve_sys_data_path(base_dir)]
        self._all_items = []
        for path in candidates:
            self.mdb_path = path
            self._load_one()
            if self._all_items:
                return

    def _load_one(self) -> None:
        self._items.clear()
        self._groups.clear()
        self._by_do_proc.clear()
        self._mainmenu_groups.clear()
        if not os.path.exists(self.mdb_path):
            return

        backend = get_backend_for_path(self.mdb_path)
        # program 表實體欄位（相容 Access / SQLite 遷移命名）
        col_prg_group = self._pick_table_column(
            backend, "program", "PRG_GROUP", "Prg_Group"
        )
        col_do_proc = self._pick_table_column(backend, "program", "DO_PROC", "Do_Proc")
        col_chn = self._pick_table_column(backend, "program", "CHN_TITLE", "Chn_Title")
        col_eng = self._pick_table_column(backend, "program", "ENG_TITLE", "Eng_Title")
        col_need_do = self._pick_table_column(backend, "program", "NEED_DO", "Need_Do")
        col_item_no = self._pick_table_column(
            backend, "program", "ITEM_NO", "ItemNumber", "Item_No", "ITEMNUMBER"
        )
        col_work_file = self._pick_table_column(backend, "program", "WORK_FILE", "Work_File")
        col_tx_file = self._pick_table_column(backend, "program", "TX_FILE", "Tx_File")
        col_level = self._pick_table_column(backend, "program", "LEVEL", "Level")
        col_proc_name = self._pick_table_column(backend, "program", "PROC_NAME", "Proc_Name")
        col_key_code = self._pick_table_column(backend, "program", "KEY_CODE", "Key_Code")
        col_num_type = self._pick_table_column(backend, "program", "NUM_TYPE", "Num_Type")
        col_num_control = self._pick_table_column(
            backend, "program", "NUM_CONTROL", "Num_Control"
        )
        col_num_digit = self._pick_table_column(backend, "program", "NUM_DIGIT", "Num_Digit")
        col_num_separate = self._pick_table_column(
            backend,
            "program",
            "NUM_SEPARATE",
            "Num_Separate",
            # 舊庫常見拼寫錯誤 SEPERATE
            "NUM_SEPERATE",
            "Num_Seperate",
        )
        col_work_db = self._pick_table_column(backend, "program", "WORK_DB", "Work_Db")
        col_co_key = self._pick_table_column(
            backend, "program", "PRG_CO", "Prg_Co", "CO_KEY", "Co_Key"
        )
        col_work_proc = self._pick_table_column(backend, "program", "WORK_PROC", "Work_Proc")
        col_need_attach = self._pick_table_column(
            backend, "program", "NEED_ATTACH", "Need_Attach"
        )
        col_attach_path = self._pick_table_column(
            backend, "program", "ATTACH_PATH", "Attach_Path"
        )
        col_attach_key = self._pick_table_column(
            backend, "program", "ATTACH_KEY", "Attach_Key"
        )
        col_need_other = self._pick_table_column(
            backend, "program", "NEED_OTHER", "Need_Other"
        )
        col_other_title = self._pick_table_column(
            backend, "program", "OTHER_TITLE", "Other_Title"
        )
        col_std_proc = self._pick_table_column(
            backend, "program", "STD_PROC", "Std_Proc", "STD_PORC", "Std_Porc"
        )

        if not col_prg_group or not col_do_proc:
            return

        do_c = col_do_proc
        key_code_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_key_code).items()
        }
        num_type_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_num_type).items()
        }
        num_control_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_num_control).items()
        }
        num_digit_by_do = {
            k: int(v)  # type: ignore[arg-type]
            for k, v in self._column_map_by_do(
                backend, do_c, col_num_digit, as_int=True, default_int=8
            ).items()
        }
        num_separate_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_num_separate).items()
        }
        work_db_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_work_db).items()
        }
        co_key_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_co_key).items()
        }
        work_proc_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_work_proc).items()
        }
        need_attach_by_do = {
            k: bool(v)
            for k, v in self._column_map_by_do(
                backend, do_c, col_need_attach, as_bool=True
            ).items()
        }
        attach_path_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_attach_path).items()
        }
        attach_key_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_attach_key).items()
        }
        need_other_by_do = {
            k: bool(v)
            for k, v in self._column_map_by_do(
                backend, do_c, col_need_other, as_bool=True
            ).items()
        }
        other_title_by_do = {
            k: str(v or "")
            for k, v in self._column_map_by_do(backend, do_c, col_other_title).items()
        }
        std_proc_by_do = {
            k: bool(v)
            for k, v in self._column_map_by_do(
                backend, do_c, col_std_proc, as_bool=True, default_bool=True
            ).items()
        }

        g = self._q_col(col_prg_group)
        d = self._q_col(col_do_proc)
        chn = self._q_col(col_chn) if col_chn else "NULL"
        eng = self._q_col(col_eng) if col_eng else "NULL"
        need = self._q_col(col_need_do) if col_need_do else "1"
        wf = self._q_col(col_work_file) if col_work_file else "NULL"
        tx = self._q_col(col_tx_file) if col_tx_file else "NULL"
        item_sql = self._q_col(col_item_no) if col_item_no else None
        has_item_no = col_item_no is not None
        has_level = col_level is not None
        has_proc_name = col_proc_name is not None
        level_sel = (
            f", {self._q_col(col_level)} AS PRG_LEVEL" if has_level else ", NULL AS PRG_LEVEL"
        )
        proc_sel = (
            f", {self._q_col(col_proc_name)} AS PRG_PROC_NAME"
            if has_proc_name
            else ", NULL AS PRG_PROC_NAME"
        )
        # 按 PRG_GROUP 及 ITEM_NO／ItemNumber 順序
        order_by = (
            f"{g}, {self._q_col(col_item_no)}"
            if has_item_no and col_item_no
            else f"{g}, {d}"
        )
        if has_item_no and item_sql:
            sql = (
                f"SELECT {g}, {d}, {wf}, {tx}, {chn}, {eng}, {need}, {item_sql}"
                f"{level_sel}{proc_sel} "
                f"FROM program ORDER BY {order_by}"
            )
        else:
            sql = (
                f"SELECT {g}, {d}, {wf}, {tx}, {chn}, {eng}, {need}"
                f"{level_sel}{proc_sel} "
                f"FROM program ORDER BY {order_by}"
            )

        _cols, program_rows = backend.fetch_rows_sql(sql, limit=5000)
        auto_order = 0
        for row in program_rows:
            prg_group = str(row[0]).strip() if row[0] is not None else ""
            do_proc = str(row[1]).strip() if row[1] is not None else ""
            work_file = str(row[2]).strip() if row[2] is not None else ""
            tx_file = str(row[3]).strip() if len(row) > 3 and row[3] is not None else ""
            chn_title = str(row[4]).strip() if len(row) > 4 and row[4] is not None else ""
            eng_title = str(row[5]).strip() if len(row) > 5 and row[5] is not None else ""
            need_do_raw = row[6] if len(row) > 6 else False
            need_do = self._bool_flag(need_do_raw) if col_need_do else True

            # NEED_DO 為 FALSE 則不讀取
            if not need_do:
                continue
            if not do_proc:
                continue

            if has_item_no:
                order_no = parse_level_value(row[7]) if len(row) > 7 else None
                if order_no is None:
                    order_no = auto_order
                level_col = 8
            else:
                order_no = auto_order
                level_col = 7

            req_level: Optional[int] = None
            if has_level and len(row) > level_col and row[level_col] is not None:
                req_level = parse_level_value(row[level_col])

            proc_col = level_col + 1
            pr_proc_raw = row[proc_col] if len(row) > proc_col else None
            prog_proc_name = (
                str(pr_proc_raw).strip() if pr_proc_raw is not None else ""
            )
            prog_proc_name = prog_proc_name or None

            auto_order += 1
            dp_key = do_proc.strip().upper()
            kc_val = (key_code_by_do.get(dp_key) or "").strip()
            prog_item = ProgramItem(
                group=prg_group,
                do_proc=do_proc,
                work_file=work_file or None,
                tx_file=tx_file or None,
                chn_title=chn_title,
                eng_title=eng_title,
                need_do=need_do,
                order_no=order_no,
                required_level=req_level,
                proc_name=prog_proc_name,
                key_code=kc_val or None,
                num_type=(num_type_by_do.get(dp_key) or "").strip() or None,
                num_control=(num_control_by_do.get(dp_key) or "").strip() or None,
                num_digit=int(num_digit_by_do.get(dp_key, 8)),
                num_separate=num_separate_by_do.get(dp_key),
                work_db=(work_db_by_do.get(dp_key) or "").strip() or None,
                co_key=(co_key_by_do.get(dp_key) or "").strip() or None,
                work_proc=(work_proc_by_do.get(dp_key) or "").strip() or None,
                need_attach=need_attach_by_do.get(dp_key, False),
                attach_path=(attach_path_by_do.get(dp_key) or "").strip() or None,
                attach_key=(attach_key_by_do.get(dp_key) or "").strip() or None,
                need_other=need_other_by_do.get(dp_key, False),
                other_title=(other_title_by_do.get(dp_key) or "").strip() or None,
                std_proc=std_proc_by_do.get(dp_key, True),
            )
            self._items.append(prog_item)
            self._groups.setdefault(prg_group, []).append(prog_item)

        # 依 PRG_GROUP 內部 ITEM_NO／ItemNumber 排序
        for g_items in self._groups.values():
            g_items.sort(key=lambda x: (x.order_no, x.do_proc))

        self._rebuild_by_do_proc()
        # 再載入 MAINMENU，建立 mainmenu_groups
        self._load_mainmenu(backend)
        self._all_items = list(self._items)

    def _load_mainmenu(self, backend: DbBackendBase) -> None:
        """
        讀取 MAINMENU 表，結合 program.PRG_GROUP:
        - MAINMENU：MENU_TYPE、SEQ_NO、CHN_TITLE、ENG_TITLE、NEED_DO
        - program.PRG_GROUP 對應 MENU_TYPE
        NEED_DO 為 FALSE 則不讀取；僅保留底下仍有 ProgramItem 的群組。
        """
        mm_table = None
        for cand in ("MAINMENU", "MainMenu", "mainmenu"):
            if backend.list_columns(cand):
                mm_table = cand
                break
        if not mm_table:
            self._append_mainmenu_from_prg_groups()
            return

        col_menu_type = self._pick_table_column(
            backend, mm_table, "MENU_TYPE", "Menu_Type"
        )
        col_seq = self._pick_table_column(backend, mm_table, "SEQ_NO", "Seq_No")
        col_chn = self._pick_table_column(backend, mm_table, "CHN_TITLE", "Chn_Title")
        col_eng = self._pick_table_column(backend, mm_table, "ENG_TITLE", "Eng_Title")
        col_need = self._pick_table_column(backend, mm_table, "NEED_DO", "Need_Do")
        if not col_menu_type:
            self._append_mainmenu_from_prg_groups()
            return

        mt = self._q_col(col_menu_type)
        seq = self._q_col(col_seq) if col_seq else "0"
        chn = self._q_col(col_chn) if col_chn else "NULL"
        eng = self._q_col(col_eng) if col_eng else "NULL"
        need = self._q_col(col_need) if col_need else "1"
        order_sql = f"ORDER BY {seq}, {mt}" if col_seq else f"ORDER BY {mt}"
        _cols, menu_rows = backend.fetch_rows_sql(
            f"SELECT {mt}, {seq}, {chn}, {eng}, {need} FROM {mm_table} {order_sql}",
            limit=1000,
        )
        if not menu_rows:
            self._append_mainmenu_from_prg_groups()
            return

        for row in menu_rows:
            menu_type = str(row[0]).strip() if row[0] is not None else ""
            if not menu_type:
                continue
            try:
                seq_no = int(row[1]) if row[1] is not None else 0
            except Exception:
                seq_no = 0
            chn_title = str(row[2]).strip() if row[2] is not None else ""
            eng_title = str(row[3]).strip() if row[3] is not None else ""
            need_do = self._bool_flag(row[4]) if col_need else True
            if not need_do:
                continue

            items = self._items_for_menu_type(menu_type)
            if not items:
                continue

            self._mainmenu_groups.append(
                MainMenuGroup(
                    menu_type=menu_type,
                    seq_no=seq_no,
                    chn_title=chn_title,
                    eng_title=eng_title,
                    need_do=need_do,
                    items=list(items),
                )
            )

        if not self._mainmenu_groups and self._groups:
            self._append_mainmenu_from_prg_groups()

        self._mainmenu_groups.sort(key=lambda g: (g.seq_no, g.menu_type))

    def apply_permission_filter(
        self,
        user_group_level: Optional[int],
        session_company_key: Optional[str] = None,
    ) -> None:
        """
        依 SYS_GROUP.GROUP_LEVEL 篩選：若 PROGRAM.LEVEL 有值，需 user_group_level <= LEVEL。
        另依 PROGRAM.PRG_CO 篩選：登入公司須在 PRG_CO 清單內（單一值須完全相符）。
        """
        from core.db_factory import resolve_program_company_key

        source = self._all_items or self._items

        def allowed(p: ProgramItem) -> bool:
            if user_group_level is not None:
                if p.required_level is not None and user_group_level > p.required_level:
                    return False
            if session_company_key:
                _key, err = resolve_program_company_key(
                    p.co_key or "", session_company_key
                )
                if err:
                    return False
            return True

        self._items = [p for p in source if allowed(p)]
        self._groups.clear()
        for p in self._items:
            self._groups.setdefault(p.group, []).append(p)
        for g_items in self._groups.values():
            g_items.sort(key=lambda x: (x.order_no, x.do_proc))
        self._rebuild_by_do_proc()

        valid: Set[Tuple[str, str]] = {
            (p.group.strip().upper(), p.do_proc.strip().upper()) for p in self._items
        }
        new_mm: List[MainMenuGroup] = []
        for g in self._mainmenu_groups:
            ni = [
                it
                for it in g.items
                if (it.group.strip().upper(), it.do_proc.strip().upper()) in valid
            ]
            if ni:
                new_mm.append(
                    MainMenuGroup(
                        menu_type=g.menu_type,
                        seq_no=g.seq_no,
                        chn_title=g.chn_title,
                        eng_title=g.eng_title,
                        need_do=g.need_do,
                        items=ni,
                    )
                )
        self._mainmenu_groups = new_mm
        self._mainmenu_groups.sort(key=lambda g: (g.seq_no, g.menu_type))

    def find_program_item(self, proc: str) -> Optional[ProgramItem]:
        """
        依 DO_PROC 或 PROC_NAME（Proc_Name）尋找程式定義。
        選單通常用 DO_PROC=Quotation；列印/舊連結可能用 Proc_Name=DO_QUOTATION。
        """
        key = (proc or "").strip().upper()
        if not key:
            return None
        candidates: List[ProgramItem] = []
        for item in self._all_items:
            if item.do_proc.strip().upper() == key:
                candidates.append(item)
                continue
            if (item.proc_name or "").strip().upper() == key:
                candidates.append(item)
        if not candidates:
            return None
        # 優先：有 TX_FILE > 有 WORK_FILE > 第一筆
        candidates.sort(
            key=lambda x: (
                1 if x.tx_file else 0,
                1 if x.work_file else 0,
                -x.order_no,
            ),
            reverse=True,
        )
        return candidates[0]

    def find_by_do_proc(self, do_proc: str) -> Optional[ProgramItem]:
        """相容舊介面；同 find_program_item。"""
        return self.find_program_item(do_proc)

    def find_allowed_program_item(self, proc: str) -> Optional[ProgramItem]:
        """僅在已通過權限篩選的選單項目中尋找（避免繞過 LEVEL / PRG_CO）。"""
        key = (proc or "").strip().upper()
        if not key:
            return None
        candidates: List[ProgramItem] = []
        for item in self._items:
            if item.do_proc.strip().upper() == key:
                candidates.append(item)
                continue
            if (item.proc_name or "").strip().upper() == key:
                candidates.append(item)
        if not candidates:
            return None
        candidates.sort(
            key=lambda x: (
                1 if x.tx_file else 0,
                1 if x.work_file else 0,
                -x.order_no,
            ),
            reverse=True,
        )
        return candidates[0]

    @staticmethod
    def _program_item_for_database(
        menu_item: Optional[ProgramItem],
        resolved_item: Optional[ProgramItem],
    ) -> Optional[ProgramItem]:
        """
        決定 WORK_DB / CO_KEY 取自哪一列。
        選單列（如 DO_USER）常僅設 WORK_PROC，實際 WORK_DB 在 WORK_PROC 對應列。
        """
        for p in (resolved_item, menu_item):
            if p is None:
                continue
            if (p.work_db or "").strip() or (p.co_key or "").strip():
                return p
        return resolved_item or menu_item

    def resolve_work_file_for_do_proc(self, do_proc: str) -> Tuple[str, str]:
        """
        解析規則：DO_PROC -> WORK_PROC（可多層）-> WORK_FILE。
        回傳 (table_name, rule_proc)；rule_proc 供 columns.DBF_NAME 使用。
        """
        binding = self.resolve_program_binding(do_proc)
        return binding.work_file, binding.rule_proc

    def resolve_program_binding(self, do_proc: str) -> ProgramBinding:
        """
        自 PROGRAM（應已自 sys_data.mdb 即時載入）解析：
        WORK_PROC、WORK_FILE、columns 用 DBF_NAME（WORK_PROC）、WORK_DB 所在列。
        """
        key = (do_proc or "").strip().upper()
        menu_item = self.find_program_item(do_proc)
        if menu_item is None:
            return ProgramBinding(None, None, do_proc, do_proc)

        source_proc = (menu_item.do_proc or "").strip() or do_proc
        rule_proc = (menu_item.work_proc or "").strip() or source_proc
        work_file = (menu_item.work_file or "").strip()

        visited: Set[str] = {key}
        proc_key = rule_proc.strip().upper()
        for _ in range(8):
            if not proc_key or proc_key in visited:
                break
            visited.add(proc_key)
            target = self.find_program_item(proc_key)
            if target is None:
                break
            rule_proc = (target.do_proc or "").strip() or proc_key
            wf = (target.work_file or "").strip()
            if wf:
                work_file = wf
                break
            next_proc = (target.work_proc or "").strip()
            if not next_proc or next_proc.upper() == proc_key:
                break
            proc_key = next_proc.upper()
            rule_proc = next_proc

        if not work_file:
            work_file = rule_proc or source_proc

        resolved_item = self.find_program_item(rule_proc)
        data_item = self._program_item_for_database(menu_item, resolved_item)
        return ProgramBinding(
            menu_item=menu_item,
            data_item=data_item,
            work_file=work_file,
            rule_proc=rule_proc,
        )

    def list_tx_files_by_do_proc(self, do_proc: str) -> List[str]:
        """
        回傳同一 DO_PROC 在 program 表所有設定過的 TX_FILE（去重後）。
        這可避免同一 DO_PROC 多筆記錄時，單筆匹配漏掉 TX_FILE。
        """
        key = do_proc.strip().upper()
        out: List[str] = []
        seen = set()
        for item in self._all_items:
            if item.do_proc.strip().upper() != key:
                continue
            if not item.tx_file:
                continue
            raw = item.tx_file.replace(";", ",").replace("|", ",").replace("，", ",")
            for part in raw.split(","):
                name = part.strip()
                if not name:
                    continue
                u = name.upper()
                if u in seen:
                    continue
                seen.add(u)
                out.append(name)

        # 保底：若快取沒有，直接查 sys_data.mdb.program（不受目前已載入清單限制）
        if not out and os.path.exists(self.mdb_path):
            backend = get_backend_for_path(self.mdb_path)
            _cols, rows = backend.fetch_rows_sql("SELECT DO_PROC, TX_FILE FROM program", limit=5000)
            for row in rows:
                do_proc_raw = str(row[0]).strip() if row and row[0] is not None else ""
                if do_proc_raw.upper() != key:
                    continue
                raw_val = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
                if not raw_val:
                    continue
                raw = raw_val.replace(";", ",").replace("|", ",").replace("，", ",")
                for part in raw.split(","):
                    name = part.strip()
                    if not name:
                        continue
                    u = name.upper()
                    if u in seen:
                        continue
                    seen.add(u)
                    out.append(name)
        return out


