from __future__ import annotations

import os
from dataclasses import dataclass, field
import io
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.auth import (
    UserSession,
    authenticate,
    detect_last_company_by_credentials,
    load_available_company_keys,
    record_login_success,
    resolve_sys_data_path,
    resolve_user_data_path,
)
from core.data_dictionary import (
    ColumnTitle,
    DataDictionary,
    LanguageCode,
    WorkActionFlags,
    resolve_work_actions_for_program,
)
from core.db_backend import DbBackendBase
from core.db_factory import (
    get_backend_for_path,
    resolve_company_db_path,
    resolve_metadata_db_path,
    resolve_program_company_key,
    ensure_company_db_path,
    prepare_transfer_db_for_import,
    validate_company_db,
)
from core.display_format import (
    format_cell_display,
    grid_column_align,
    is_boolean_data_type,
    normalize_storage_value,
)
from core.arap_settlement_service import (
    SettlementDocument,
    SettlementHeader,
    SettlementLine,
    auto_settle_lines,
    filter_lines,
    find_line_index,
    is_arap_settlement_program,
    load_settlement,
    remaining_settlement,
    save_settlement,
    sum_totals,
)
from core.receipt_payment_service import (
    document_from_dict as receipt_payment_from_dict,
    document_to_dict as receipt_payment_to_dict,
    is_receipt_payment_program,
    load_receipt_payment,
    save_receipt_payment,
)
from core.party_query_service import (
    PartyInfo,
    PartyQueryDocument,
    PartyQueryLine,
    TX_KIND_OPTIONS,
    current_party,
    filter_party_lines,
    find_line_index as find_party_line_index,
    is_party_query_program,
    load_party_query,
    totals_dict as party_totals_dict,
)
from core.stock_query_service import (
    StockInfo,
    StockQueryDocument,
    StockQueryLine,
    TX_KIND_OPTIONS as STOCK_TX_KIND_OPTIONS,
    current_stock,
    filter_stock_lines,
    find_line_index as find_stock_line_index,
    is_stock_query_program,
    load_stock_query,
    totals_dict as stock_totals_dict,
)
from core.account_query_service import (
    AccountInfo,
    AccountQueryDocument,
    AccountQueryLine,
    TX_KIND_OPTIONS as ACCOUNT_TX_KIND_OPTIONS,
    current_account,
    filter_account_lines,
    find_line_index as find_account_line_index,
    is_account_query_program,
    load_account_query,
    totals_dict as account_totals_dict,
)
from core.attachment_messages import (
    format_attach_not_found_message,
    user_may_see_attach_folder,
)
from core.attachment_service import (
    is_image_path,
    is_pdf_path,
    resolve_attachments_for_row,
)
from core.data_import_service import (
    data_import_result_dict,
    is_data_import_program,
    list_import_kind_options,
    list_import_source_folders,
    list_pending_import_grid,
    list_pending_import_rows,
    run_data_import,
)
from core.program_dispatch import is_standard_program
from core.menu_loader import MainMenuGroup, ProgramItem, ProgramRepository
from core.record_key_service import (
    ManualKeyRequired,
    ProgramNumberConfig,
    config_from_program,
    merge_allocated_key_fields,
    prepare_record_key_values,
    resolve_program_number_config,
)
from core.row_insert_defaults import apply_insert_bit_defaults
from core.row_where import delete_tx_rows_for_master, resolve_update_where
from core.tx_row_order import renumber_item_no


@dataclass
class WorkSchema:
    """開啟作業時回傳的結構定義。"""

    do_proc: str
    table_name: str
    rule_proc: str
    db_path: str
    grid_fields: List[str]
    form_fields: List[str]
    physical_fields: List[str]
    tx_files: List[str]
    menu_title: str
    columns: List[Dict[str, Any]]
    form_columns: List[Dict[str, Any]] = field(default_factory=list)
    print_doc_key_column: Optional[str] = None
    work_actions: WorkActionFlags = field(default_factory=WorkActionFlags)
    key_code_column: Optional[str] = None
    num_type_column: Optional[str] = None
    num_control_column: Optional[str] = None
    num_digit: int = 8
    proc_name: Optional[str] = None


@dataclass
class AppRuntime:
    """單一登入 session 的執行環境。"""

    base_dir: str
    session: UserSession
    lang: LanguageCode = "CHN"
    mdb_path: str = ""
    user_data_path: str = ""
    data_dict: DataDictionary = field(init=False)
    program_repo: ProgramRepository = field(init=False)
    _program_loaded: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.base_dir = os.path.abspath(self.base_dir)
        if not self.mdb_path:
            self.mdb_path = resolve_sys_data_path(self.base_dir)
        if not self.user_data_path:
            self.user_data_path = self.session.user_data_path
        self.data_dict = DataDictionary(self.mdb_path)
        self.program_repo = ProgramRepository(self.mdb_path)

    def reload_metadata(self) -> None:
        new_sys = resolve_sys_data_path(self.base_dir)
        if new_sys != self.mdb_path:
            self.mdb_path = new_sys
            self.data_dict.mdb_path = new_sys
            self.program_repo.mdb_path = new_sys
        self.data_dict.load()
        self.program_repo.load()
        self.program_repo.apply_permission_filter(
            self.session.group_level, self.session.company_key
        )
        self._program_loaded = True

    def close(self) -> None:
        """Web session 結束；共用 ODBC 連線由 access_pool 管理，不在此關閉。"""
        self._program_loaded = False


class AppService:
    """桌面與 Web 共用的業務邏輯。"""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)

    def list_companies(self) -> Tuple[List[str], Optional[str]]:
        user_data_path = resolve_user_data_path(self.base_dir)
        keys, err, _missing = load_available_company_keys(
            self.base_dir, user_data_path
        )
        return keys, err

    def detect_last_company(
        self, user_no: str, password: str
    ) -> Tuple[Optional[str], Optional[str]]:
        user_data_path = resolve_user_data_path(self.base_dir)
        last_co, err = detect_last_company_by_credentials(user_data_path, user_no, password)
        if err or not last_co:
            return last_co, err
        if validate_company_db(self.base_dir, last_co):
            return None, None
        return last_co, None

    def login(
        self,
        user_no: str,
        password: str,
        company_key: str,
        *,
        login_date: str = "",
        record_success: bool = True,
    ) -> Tuple[Optional[AppRuntime], Optional[str]]:
        user_data_path = resolve_user_data_path(self.base_dir)
        co = (company_key or "").strip()
        if co:
            db_err = validate_company_db(self.base_dir, co)
            if db_err:
                return None, db_err
        session, err = authenticate(user_data_path, user_no, password, company_key)
        if err or session is None:
            return None, err or "登入失敗。"
        if login_date:
            session.login_date = login_date.strip()
        if not co:
            db_err = validate_company_db(self.base_dir, session.company_key)
            if db_err:
                return None, db_err
        if record_success:
            rec_err = record_login_success(user_data_path, user_no, company_key)
            if rec_err:
                return None, rec_err
        runtime = AppRuntime(base_dir=self.base_dir, session=session)
        runtime.reload_metadata()
        return runtime, None

    def create_runtime_from_session(self, session: UserSession) -> AppRuntime:
        runtime = AppRuntime(base_dir=self.base_dir, session=session)
        runtime.reload_metadata()
        return runtime

    def menu_groups(self, runtime: AppRuntime) -> List[MainMenuGroup]:
        return runtime.program_repo.mainmenu_groups

    def set_language(self, runtime: AppRuntime, lang: LanguageCode) -> None:
        runtime.lang = lang

    def _resolve_program_db_path(
        self, runtime: AppRuntime, prg: Optional[ProgramItem]
    ) -> tuple[str, Optional[str]]:
        work_db = (getattr(prg, "work_db", None) or "").strip() if prg else ""
        if work_db:
            meta_path = resolve_metadata_db_path(runtime.base_dir, work_db)
            if meta_path:
                return meta_path, None
            if os.path.isabs(work_db):
                return work_db, None
            root, ext = os.path.splitext(work_db)
            if ext:
                cand = os.path.join(runtime.base_dir, work_db)
                if os.path.isfile(cand):
                    return cand, None
                low = work_db.lower()
                if low.endswith(".mdb"):
                    sqlite_cand = os.path.join(
                        runtime.base_dir, root + ".sqlite"
                    )
                    if os.path.isfile(sqlite_cand):
                        return sqlite_cand, None
                return cand, None
            return ensure_company_db_path(runtime.base_dir, work_db)
        prg_co = (getattr(prg, "co_key", None) or "").strip() if prg else ""
        key, err = resolve_program_company_key(prg_co, runtime.session.company_key)
        if err:
            return "", err
        return ensure_company_db_path(runtime.base_dir, key)

    @staticmethod
    def _parse_tx_files(tx_file_value: Optional[str]) -> List[str]:
        if not tx_file_value:
            return []
        raw = tx_file_value.replace(";", ",").replace("|", ",").replace("，", ",")
        out: List[str] = []
        seen = set()
        for part in raw.split(","):
            name = part.strip()
            if not name:
                continue
            key = name.upper()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
        return out

    def _backend_for_path(self, runtime: AppRuntime, db_path: str) -> DbBackendBase:
        return get_backend_for_path(db_path)

    def _column_meta_dict(
        self,
        runtime: AppRuntime,
        table_name: str,
        field_names: List[str],
    ) -> List[Dict[str, Any]]:
        lang = runtime.lang
        out: List[Dict[str, Any]] = []
        for name in field_names:
            meta: Optional[ColumnTitle] = runtime.data_dict._meta(table_name, name)
            if meta is None:
                out.append(
                    {
                        "name": name,
                        "title": name,
                        "chn_title": "",
                        "eng_title": "",
                        "data_type": "",
                        "data_format": "",
                        "edit_tab": "",
                        "edit_type": "",
                        "grid_view": True,
                        "grid_index": 0,
                        "grid_width_chars": 0,
                        "lookup_db": "",
                        "lookup_key": "",
                        "lookup_ret": "",
                        "search_ret": "",
                        "combo_list": "",
                        "ctrl_type": "",
                        "align": "left",
                    }
                )
                continue
            out.append(
                {
                    "name": meta.name,
                    "title": meta.get_title(lang),
                    "chn_title": meta.chn_title or "",
                    "eng_title": meta.eng_title or "",
                    "data_type": meta.data_type or "",
                    "data_format": meta.data_format or "",
                    "edit_tab": meta.edit_tab or "",
                    "edit_type": (meta.edit_type or "").strip().upper(),
                    "grid_view": bool(meta.grid_view),
                    "grid_index": int(meta.grid_index or 0),
                    "grid_width_chars": meta.grid_width_chars,
                    "need_attach": meta.need_attach,
                    "attach_path": meta.attach_path or "",
                    "attach_key": meta.attach_key or "",
                    "need_other": meta.need_other,
                    "other_title": meta.other_title or "",
                    "lookup_db": meta.lookup_db or "",
                    "lookup_key": meta.lookup_key or "",
                    "lookup_ret": meta.lookup_ret or "",
                    "search_ret": (meta.search_ret or "").strip(),
                    "combo_list": (meta.combo_list or "").strip(),
                    "ctrl_type": (meta.ctrl_type or "").strip(),
                    "align": grid_column_align(
                        meta.name, meta.data_format or "", meta.data_type or ""
                    ),
                }
            )
        return out

    @staticmethod
    def _work_actions_dict(flags: WorkActionFlags) -> Dict[str, Any]:
        return {
            "need_attach": bool(flags.need_attach),
            "attach_path": flags.attach_path or "",
            "attach_key": flags.attach_key or "",
            "need_other": bool(flags.need_other),
            "other_title": flags.other_title or "",
        }

    @staticmethod
    def _resolve_update_where(
        physical_fields: List[str],
        old_row: List[str],
        print_doc_key_column: Optional[str] = None,
        form_fields: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[str]]:
        return resolve_update_where(
            physical_fields,
            old_row,
            print_doc_key_column=print_doc_key_column,
            form_fields=form_fields,
        )

    def _form_values_from_row(
        self,
        runtime: AppRuntime,
        table_name: str,
        form_fields: List[str],
        physical_fields: List[str],
        physical_row: List[str],
    ) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for f in form_fields:
            try:
                i = physical_fields.index(f)
                raw = str(physical_row[i]) if i < len(physical_row) else ""
                f_fmt = runtime.data_dict.get_data_format(table_name, f)
                f_typ = runtime.data_dict.get_data_type(table_name, f)
                out[f] = format_cell_display(f, raw, f_fmt, f_typ)
            except ValueError:
                out[f] = ""
        return out

    def _resolve_master_tx_key(
        self,
        runtime: AppRuntime,
        schema: WorkSchema,
        physical_row: List[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """回傳 (鍵欄位名, 鍵值) 供 TX 明細過濾。"""
        key_col = schema.print_doc_key_column
        if key_col:
            try:
                idx = schema.physical_fields.index(key_col)
                val = (physical_row[idx] or "").strip() if idx < len(physical_row) else ""
                if val:
                    return key_col, val
            except ValueError:
                pass
        for col in schema.physical_fields:
            if col.strip().upper() == "TX_KEY":
                idx = schema.physical_fields.index(col)
                val = (physical_row[idx] or "").strip() if idx < len(physical_row) else ""
                if val:
                    return col, val
        return None, None

    def _ensure_allowed_program(
        self, runtime: AppRuntime, do_proc: str, *, reload_program: bool = False
    ) -> Tuple[Optional[ProgramItem], Optional[str]]:
        if reload_program or not runtime._program_loaded:
            runtime.program_repo.load()
            runtime.program_repo.apply_permission_filter(
                runtime.session.group_level, runtime.session.company_key
            )
            runtime._program_loaded = True
        prg = runtime.program_repo.find_allowed_program_item(do_proc)
        if prg is None:
            return None, f"無權限執行此程式或程式不存在：{do_proc}"
        return prg, None

    def _backend_for_do_proc(
        self, runtime: AppRuntime, do_proc: str, *, reload_program: bool = False
    ) -> Tuple[Optional[DbBackendBase], Optional[str]]:
        prg, err = self._ensure_allowed_program(runtime, do_proc, reload_program=reload_program)
        if err or prg is None:
            return None, err
        binding = runtime.program_repo.resolve_program_binding(do_proc)
        data_prg = binding.data_item
        db_path, co_err = self._resolve_program_db_path(runtime, data_prg or prg)
        if co_err:
            return None, co_err
        return self._backend_for_path(runtime, db_path), None

    def _resolve_data_import_folder(
        self, runtime: AppRuntime, folder: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        正規化 DATAIMPORT 來源資料夾。
        空白或指向應用目錄 WoleeWeb 時，改用業務預設（通常為 docBiz/Transfer）。
        回傳 (folder, auto_warning)。
        """
        from core.db_factory import resolve_default_transfer_folder

        req = (folder or "").strip()

        def _is_app_dir_folder(f: str) -> bool:
            raw = (f or "").strip()
            if not raw:
                return True
            leaf = raw.replace("\\", "/").rstrip("/").split("/")[-1]
            if leaf.lower() == "woleeweb":
                return True
            try:
                return os.path.abspath(raw).replace("\\", "/").lower().rstrip(
                    "/"
                ) == os.path.abspath(runtime.base_dir).replace("\\", "/").lower().rstrip(
                    "/"
                )
            except (OSError, ValueError):
                return False

        if not _is_app_dir_folder(req):
            return req, None
        default_folder, default_note = resolve_default_transfer_folder(runtime.base_dir)
        if default_folder and os.path.abspath(default_folder) != os.path.abspath(
            runtime.base_dir
        ):
            return default_folder, default_note or f"已改用業務來源：{default_folder}"
        return req or None, None

    def _backends_for_data_import(
        self,
        runtime: AppRuntime,
        do_proc: str,
        *,
        for_write: bool = False,
        folder: Optional[str] = None,
    ) -> Tuple[
        Optional[DbBackendBase],
        Optional[DbBackendBase],
        Optional[str],
        Optional[str],
        Optional[str],
    ]:
        """
        DATAIMPORT 雙庫：
        - TRANSFER：來源（指定資料夾或 base_dir 的 TRANSFER.sqlite）
        - 公司庫：目標（WORK_DB 優先，否則 CO_KEY／登入公司）

        folder：使用者選擇的來源資料夾（可依類型不同）。
        for_write：True 時檢查 TRANSFER 可寫（執行匯入）；False 僅讀取待匯入清單。

        回傳 (transfer_be, company_be, error, share_path, warning)
        """
        prg, err = self._ensure_allowed_program(runtime, do_proc)
        if err or prg is None:
            return None, None, err, None, None
        from core.db_factory import bust_sqlite_os_cache

        transfer_path, _share_path, t_err, t_warn = prepare_transfer_db_for_import(
            runtime.base_dir, for_write=for_write, folder=folder
        )
        if t_err:
            return None, None, t_err, None, None
        if for_write:
            # 匯入前再戳一次，確保讀到最新未過帳列與寫入 POSTED 同一檔
            bust_sqlite_os_cache(transfer_path)
        binding = runtime.program_repo.resolve_program_binding(do_proc)
        data_prg = binding.data_item
        company_path, c_err = self._resolve_program_db_path(runtime, data_prg or prg)
        if c_err:
            return None, None, c_err, None, None
        if not company_path or not os.path.isfile(company_path):
            return None, None, f"找不到公司資料庫：{company_path or ''}", None, None
        if for_write:
            from core.db_factory import (
                _is_sqlite_path,
                bust_sqlite_os_cache,
                prepare_sqlite_for_write,
            )

            bust_sqlite_os_cache(company_path)
            if _is_sqlite_path(company_path):
                prep_err = prepare_sqlite_for_write(company_path)
                if prep_err:
                    return None, None, f"公司庫寫入失敗：{prep_err}", None, None
        return (
            self._backend_for_path(runtime, transfer_path),
            self._backend_for_path(runtime, company_path),
            None,
            None,
            t_warn,
        )

    def resolve_work(
        self,
        runtime: AppRuntime,
        do_proc: str,
        *,
        reload_program: bool = False,
    ) -> Tuple[Optional[WorkSchema], Optional[str]]:
        if not os.path.isfile(runtime.mdb_path):
            return None, f"找不到系統資料庫：{runtime.mdb_path}"

        if reload_program or not runtime._program_loaded:
            runtime.program_repo.load()
            runtime.program_repo.apply_permission_filter(
                runtime.session.group_level, runtime.session.company_key
            )
            runtime._program_loaded = True

        prg, perm_err = self._ensure_allowed_program(runtime, do_proc)
        if perm_err or prg is None:
            return None, perm_err
        if not is_standard_program(prg):
            return None, f"「{do_proc}」為非標準作業，請使用專用功能入口。"

        binding = runtime.program_repo.resolve_program_binding(do_proc)
        prg = binding.menu_item or prg
        table_name = binding.work_file
        resolved_proc = binding.rule_proc
        data_prg = binding.data_item
        resolved_prg = runtime.program_repo.find_by_do_proc(resolved_proc)

        runtime.data_dict.set_rule_alias(table_name, resolved_proc)

        tx_files = runtime.program_repo.list_tx_files_by_do_proc(do_proc)
        if not tx_files and resolved_proc:
            tx_files = runtime.program_repo.list_tx_files_by_do_proc(resolved_proc)
        if not tx_files:
            tx_files = self._parse_tx_files(prg.tx_file if prg else None)
        if not tx_files and resolved_prg is not None:
            tx_files = self._parse_tx_files(resolved_prg.tx_file)
        for tx_table in tx_files:
            runtime.data_dict.ensure_tx_column_rules(tx_table, resolved_proc)

        db_path, co_err = self._resolve_program_db_path(runtime, data_prg or prg)
        if co_err:
            return None, co_err
        backend = self._backend_for_path(runtime, db_path)
        physical = backend.list_columns(table_name)
        if not physical:
            return (
                None,
                f"找不到資料表「{table_name}」或無法讀取欄位（資料庫：{os.path.basename(db_path)}）。",
            )
        grid_fields = runtime.data_dict.grid_columns_for_table(table_name, physical)
        form_fields = runtime.data_dict.edit_columns_for_table(table_name, physical)
        menu_title = prg.get_title(runtime.lang) if prg else do_proc
        key_col = None
        if resolved_prg and resolved_prg.key_code:
            key_col = resolved_prg.key_code.strip() or None
        if not key_col and prg and prg.key_code:
            key_col = prg.key_code.strip() or None

        work_actions = resolve_work_actions_for_program(
            runtime.data_dict,
            table_name,
            do_proc,
            prg,
            resolved_prg,
            data_prg,
        )
        num_cfg = resolve_program_number_config(runtime.program_repo, do_proc)
        proc_name = None
        if prg and getattr(prg, "proc_name", None):
            proc_name = (prg.proc_name or "").strip() or None
        if not proc_name and resolved_prg and getattr(resolved_prg, "proc_name", None):
            proc_name = (resolved_prg.proc_name or "").strip() or None
        schema = WorkSchema(
            do_proc=do_proc,
            table_name=table_name,
            rule_proc=resolved_proc,
            db_path=db_path,
            grid_fields=grid_fields,
            form_fields=form_fields,
            physical_fields=physical,
            tx_files=tx_files,
            menu_title=menu_title,
            columns=self._column_meta_dict(runtime, table_name, grid_fields),
            form_columns=self._column_meta_dict(runtime, table_name, form_fields),
            print_doc_key_column=key_col,
            work_actions=work_actions,
            key_code_column=num_cfg.key_field if num_cfg else key_col,
            num_type_column=(num_cfg.num_type_field or None) if num_cfg else None,
            num_control_column=(
                (num_cfg.num_control_field or None) if num_cfg else None
            ),
            num_digit=num_cfg.num_digit if num_cfg else 8,
            proc_name=proc_name,
        )
        return schema, None

    def schema_to_dict(self, runtime: AppRuntime, schema: WorkSchema) -> Dict[str, Any]:
        return {
            "do_proc": schema.do_proc,
            "table_name": schema.table_name,
            "menu_title": schema.menu_title,
            "fields": schema.grid_fields,
            "physical_fields": schema.physical_fields,
            "form_fields": schema.form_fields,
            "columns": schema.columns,
            "form_columns": schema.form_columns,
            "tx_files": schema.tx_files,
            "print_doc_key_column": schema.print_doc_key_column,
            "work_actions": self._work_actions_dict(schema.work_actions),
            "key_code_column": schema.key_code_column,
            "num_type_column": schema.num_type_column,
            "num_control_column": schema.num_control_column,
            "num_digit": schema.num_digit,
            "proc_name": schema.proc_name or "",
            "lang": runtime.lang,
        }

    @staticmethod
    def _grid_phys_indices(grid_fields: List[str], physical_fields: List[str]) -> List[int]:
        indices: List[int] = []
        for f in grid_fields:
            try:
                indices.append(physical_fields.index(f))
            except ValueError:
                indices.append(-1)
        return indices

    @staticmethod
    def _map_rows_to_grid(
        grid_fields: List[str], physical_fields: List[str], rows: List[List[str]]
    ) -> List[List[str]]:
        indices = AppService._grid_phys_indices(grid_fields, physical_fields)
        mapped: List[List[str]] = []
        for row in rows:
            line: List[str] = []
            for idx in indices:
                if 0 <= idx < len(row):
                    line.append(row[idx])
                else:
                    line.append("")
            mapped.append(line)
        return mapped

    def _format_rows_for_grid_display(
        self,
        runtime: AppRuntime,
        table_name: str,
        grid_fields: List[str],
        grid_rows: List[List[str]],
    ) -> List[List[str]]:
        out: List[List[str]] = []
        for row in grid_rows:
            line: List[str] = []
            for i, field in enumerate(grid_fields):
                raw = row[i] if i < len(row) else ""
                f_fmt = runtime.data_dict.get_data_format(table_name, field)
                f_typ = runtime.data_dict.get_data_type(table_name, field)
                line.append(format_cell_display(field, raw, f_fmt, f_typ))
            out.append(line)
        return out

    def fetch_rows(
        self,
        runtime: AppRuntime,
        do_proc: str,
        keyword: str = "",
        as_filter: bool = False,
        limit: int = 100000,
        *,
        reload_program: bool = False,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        schema, err = self.resolve_work(
            runtime, do_proc, reload_program=reload_program
        )
        if err or schema is None:
            return None, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        search_ret_field = None
        search_ret_value = None
        search_ret_error = None
        kw = (keyword or "").strip()
        if kw:
            from core.search_ret_lookup import resolve_search_ret_via_lookup

            search_ret_field, search_ret_value, search_ret_error = (
                resolve_search_ret_via_lookup(
                    data_dict=runtime.data_dict,
                    backend=backend,
                    table_name=schema.table_name,
                    keyword=kw,
                    lang=runtime.lang,
                )
            )
            if search_ret_error:
                return None, search_ret_error

        # SEARCH_RET 解析成功：改以目標欄位值過濾／定位
        fetch_kw = kw
        fetch_filter = as_filter
        if search_ret_field and search_ret_value:
            fetch_kw = search_ret_value
            fetch_filter = True
            # 僅掃 SEARCH_RET 目標欄
            search_idx = None
            want = search_ret_field.strip().upper()
            for i, name in enumerate(schema.physical_fields or []):
                if (name or "").strip().upper() == want:
                    search_idx = [i]
                    break
        else:
            search_idx = None

        physical_rows = backend.fetch_rows(
            schema.table_name,
            fetch_kw if fetch_filter else "",
            fetch_filter,
            limit=limit,
            column_order=schema.physical_fields,
            search_indices=search_idx if fetch_filter else None,
        )
        # 搜尋（非過濾）且有 SEARCH_RET：仍回全部列，由前端選列；此處若 as_filter=False
        # 但已用 search_ret 解析，回傳全部列並帶 resolved 資訊供前端定位
        if search_ret_field and search_ret_value and not as_filter:
            physical_rows = backend.fetch_rows(
                schema.table_name,
                "",
                False,
                limit=limit,
                column_order=schema.physical_fields,
            )
        grid_rows = self._map_rows_to_grid(
            schema.grid_fields, schema.physical_fields, physical_rows
        )
        display_rows = self._format_rows_for_grid_display(
            runtime, schema.table_name, schema.grid_fields, grid_rows
        )
        return {
            "do_proc": do_proc,
            "table_name": schema.table_name,
            "fields": schema.grid_fields,
            "physical_fields": schema.physical_fields,
            "form_fields": schema.form_fields,
            "form_columns": schema.form_columns,
            "columns": schema.columns,
            "rows": display_rows,
            "physical_rows": physical_rows,
            "total": len(grid_rows),
            "print_doc_key_column": schema.print_doc_key_column,
            "tx_files": schema.tx_files,
            "menu_title": schema.menu_title,
            "work_actions": self._work_actions_dict(schema.work_actions),
            "search_indices": search_idx,
            "search_ret_field": search_ret_field,
            "search_ret_value": search_ret_value,
            "key_code_column": schema.key_code_column,
            "num_type_column": schema.num_type_column,
            "num_control_column": schema.num_control_column,
            "num_digit": schema.num_digit,
            "proc_name": schema.proc_name or "",
        }, None

    def fetch_lookup_rows(
        self,
        runtime: AppRuntime,
        do_proc: str,
        lookup_db: str,
        keyword: str = "",
        as_filter: bool = False,
        limit: int = 5000,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """LOOKUP：以目前作業公司庫讀取 LOOKUP_DB 表。"""
        table = (lookup_db or "").strip()
        if not table:
            return None, "缺少 LOOKUP_DB。"
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        runtime.data_dict.load_columns_for_dbf(table)
        physical = backend.list_columns(table)
        if not physical:
            return None, f"找不到資料表「{table}」或無法讀取欄位。"
        grid_fields = runtime.data_dict.grid_columns_for_table(table, physical)
        if not grid_fields:
            grid_fields = list(physical)
        physical_rows = backend.fetch_rows(
            table, keyword, as_filter, limit=limit, column_order=physical
        )
        grid_rows = self._map_rows_to_grid(grid_fields, physical, physical_rows)
        display_rows = self._format_rows_for_grid_display(
            runtime, table, grid_fields, grid_rows
        )
        return {
            "lookup_db": table,
            "fields": grid_fields,
            "physical_fields": physical,
            "columns": self._column_meta_dict(runtime, table, grid_fields),
            "rows": display_rows,
            "physical_rows": physical_rows,
            "total": len(grid_rows),
        }, None

    def insert_row(
        self,
        runtime: AppRuntime,
        do_proc: str,
        values: Dict[str, str],
        *,
        manual_key: str = "",
        skip_key_prepare: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return False, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        if not skip_key_prepare:
            num_cfg = resolve_program_number_config(runtime.program_repo, do_proc)
            try:
                prepared = prepare_record_key_values(
                    backend,
                    schema.table_name,
                    schema.physical_fields,
                    num_cfg,
                    dict(values),
                    is_new=True,
                    manual_key=manual_key,
                )
            except ManualKeyRequired:
                return False, "MANUAL_KEY_REQUIRED"
            except ValueError as ex:
                return False, str(ex) or "編號重複或無效。"
            values = prepared
        field_names = [f for f in schema.form_fields if f in values]
        row_values = []
        for f in field_names:
            raw = values.get(f, "")
            f_fmt = runtime.data_dict.get_data_format(schema.table_name, f)
            f_typ = runtime.data_dict.get_data_type(schema.table_name, f)
            row_values.append(normalize_storage_value(f, f_fmt, raw, f_typ))
        num_cfg = resolve_program_number_config(runtime.program_repo, do_proc)
        if num_cfg is not None and num_cfg.auto_numbering:
            field_names, row_values = merge_allocated_key_fields(
                field_names,
                row_values,
                num_cfg,
                values,
                schema.physical_fields,
            )
        field_names, row_values = apply_insert_bit_defaults(
            schema.physical_fields,
            field_names,
            row_values,
            is_boolean_column=lambda f: is_boolean_data_type(
                runtime.data_dict.get_data_type(schema.table_name, f)
            ),
        )
        ok = backend.insert_one(schema.table_name, field_names, row_values)
        if not ok:
            return False, getattr(backend, "last_error", "") or "新增失敗。"
        return True, None

    def prepare_save_key(
        self,
        runtime: AppRuntime,
        do_proc: str,
        values: Dict[str, str],
        mode: str,
        *,
        manual_key: str = "",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        mode_l = (mode or "").strip().lower()
        if mode_l not in ("add", "copy"):
            return {"values": dict(values), "manual_required": False}, None
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        num_cfg = resolve_program_number_config(runtime.program_repo, do_proc)
        try:
            prepared = prepare_record_key_values(
                backend,
                schema.table_name,
                schema.physical_fields,
                num_cfg,
                dict(values),
                is_new=True,
                manual_key=manual_key,
            )
            return {"values": prepared, "manual_required": False}, None
        except ManualKeyRequired as ex:
            label = runtime.data_dict.get_title(
                schema.table_name, ex.key_field, runtime.lang
            )
            lookup_db, _lookup_key, lookup_ret = runtime.data_dict.get_lookup(
                schema.table_name, ex.key_field
            )
            if not (lookup_db or "").strip():
                lookup_db = schema.table_name
            if not (lookup_ret or "").strip():
                lookup_ret = ex.key_field
            return {
                "values": dict(values),
                "manual_required": True,
                "key_field": ex.key_field,
                "key_label": label or ex.key_field,
                "suggested_key": ex.suggested_key,
                "lookup_db": lookup_db,
                "lookup_ret": lookup_ret,
                "table_name": schema.table_name,
            }, None
        except ValueError as ex:
            return None, str(ex) or "編號重複或無效。"

    def update_row(
        self,
        runtime: AppRuntime,
        do_proc: str,
        new_values: Dict[str, str],
        old_row: List[str],
    ) -> Tuple[bool, Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return False, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        set_fields = [f for f in schema.form_fields if f in new_values]
        set_values = []
        for f in set_fields:
            raw = new_values.get(f, "")
            f_fmt = runtime.data_dict.get_data_format(schema.table_name, f)
            f_typ = runtime.data_dict.get_data_type(schema.table_name, f)
            set_values.append(normalize_storage_value(f, f_fmt, raw, f_typ))
        where_fields, where_vals = self._resolve_update_where(
            schema.physical_fields,
            old_row,
            schema.print_doc_key_column,
        )
        ok = backend.update_one(
            schema.table_name,
            set_fields,
            set_values,
            where_fields,
            where_vals,
        )
        if not ok:
            return False, getattr(backend, "last_error", "") or "更新失敗。"
        return True, None

    def delete_row(
        self,
        runtime: AppRuntime,
        do_proc: str,
        old_row: List[str],
    ) -> Tuple[bool, Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return False, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        where_fields, where_vals = self._resolve_update_where(
            schema.physical_fields,
            old_row,
            schema.print_doc_key_column,
        )
        if not where_fields or not where_vals:
            return False, "找不到可刪除的主鍵。"
        tx_ok, tx_err = delete_tx_rows_for_master(
            backend,
            schema.tx_files,
            where_fields[0],
            where_vals[0],
        )
        if not tx_ok:
            return False, tx_err or "刪除交易明細失敗。"
        ok = backend.delete_one(schema.table_name, where_fields, where_vals)
        if not ok:
            return False, getattr(backend, "last_error", "") or "刪除失敗。"
        return True, None

    def prepare_ai_command_work(
        self, runtime: AppRuntime
    ) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        """確保 AI_COMMAND 表／COLUMNS／PROGRAM，並重載 metadata 供 GRID 開啟。"""
        from core.ai_command_service import (
            AI_COMMAND_DO_PROC,
            AI_COMMAND_TABLE,
            ensure_ai_command_infra,
        )

        ok, err = ensure_ai_command_infra(runtime.base_dir, runtime.mdb_path)
        if not ok:
            return None, err or "無法準備 AI_COMMAND。"
        runtime.reload_metadata()
        runtime.data_dict.load_columns_for_dbf(AI_COMMAND_TABLE)
        chn = str(runtime.lang or "").upper().startswith("C")
        title = "AI 指令" if chn else "AI Commands"
        prg = runtime.program_repo.find_allowed_program_item(AI_COMMAND_DO_PROC)
        if prg is None:
            # 權限篩選後可能被擋；再從全量找並暫加到允許清單
            prg = runtime.program_repo.find_program_item(AI_COMMAND_DO_PROC)
            if prg is not None and prg not in runtime.program_repo._items:  # noqa: SLF001
                runtime.program_repo._items.append(prg)  # noqa: SLF001
        if prg is not None:
            title = prg.get_title(runtime.lang) or title
        return {
            "do_proc": AI_COMMAND_DO_PROC,
            "title": title,
            "table_name": AI_COMMAND_TABLE,
        }, None

    def prepare_run_query(
        self, runtime: AppRuntime
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        from core.run_query_service import (
            RUN_QUERY_DO_PROC,
            RUN_QUERY_TABLE,
            RUN_QUERY_VISIBLE_ROWS,
            db_kind_options,
            default_company_sqlite_spec,
            ensure_run_query_infra,
        )

        ok, err = ensure_run_query_infra(runtime.base_dir, runtime.mdb_path)
        if not ok:
            return None, err or "無法準備 RUN_QUERY。"
        runtime.reload_metadata()
        try:
            runtime.data_dict.load_columns_for_dbf(RUN_QUERY_TABLE)
        except Exception:
            pass
        chn = str(runtime.lang or "").upper().startswith("C")
        title = "執行查詢" if chn else "Execute Query"
        prg = runtime.program_repo.find_allowed_program_item(RUN_QUERY_DO_PROC)
        if prg is None:
            for alias in ("RunQuery", "DO_RUNQUERY", "RUN_QUERY"):
                prg = runtime.program_repo.find_program_item(alias) or runtime.program_repo.find_allowed_program_item(alias)
                if prg is not None:
                    break
        if prg is not None:
            title = prg.get_title(runtime.lang) or title
        spec = default_company_sqlite_spec(
            runtime.base_dir, str(runtime.session.company_key or "GS")
        )
        return {
            "do_proc": RUN_QUERY_DO_PROC,
            "title": title,
            "table_name": RUN_QUERY_TABLE,
            "visible_rows": RUN_QUERY_VISIBLE_ROWS,
            "db_kinds": db_kind_options(chn=chn),
            "default_kind": spec.normalized_kind(),
            "default_path": spec.path or "",
        }, None

    def run_query_test_connection(
        self, runtime: AppRuntime, conn: Dict[str, Any]
    ) -> Tuple[bool, str]:
        from core.run_query_service import DbConnectionSpec, test_connection

        spec = DbConnectionSpec(
            kind=str(conn.get("kind") or ""),
            path=str(conn.get("path") or ""),
            host=str(conn.get("host") or "localhost"),
            port=int(conn.get("port") or 0),
            database=str(conn.get("database") or ""),
            user=str(conn.get("user") or ""),
            password=str(conn.get("password") or ""),
            driver=str(conn.get("driver") or ""),
        )
        return test_connection(spec)

    def run_query_execute(
        self, runtime: AppRuntime, sql: str, conn: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        from core.run_query_service import DbConnectionSpec, execute_sql

        spec = DbConnectionSpec(
            kind=str(conn.get("kind") or ""),
            path=str(conn.get("path") or ""),
            host=str(conn.get("host") or "localhost"),
            port=int(conn.get("port") or 0),
            database=str(conn.get("database") or ""),
            user=str(conn.get("user") or ""),
            password=str(conn.get("password") or ""),
            driver=str(conn.get("driver") or ""),
        )
        data, err = execute_sql(spec, sql)
        if err or data is None:
            return None, err or "執行失敗。"
        return {
            "columns": list(data.columns or []),
            "rows": [list(r) for r in (data.rows or [])],
            "sql": data.sql,
            "total": int(data.total),
            "rowcount": int(data.rowcount),
            "is_result_set": bool(data.is_result_set),
            "message": data.message or "",
        }, None

    def run_query_save(
        self,
        runtime: AppRuntime,
        sql: str,
        description: str = "",
        code: str = "",
    ) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        from core.run_query_service import save_run_query

        rec, err = save_run_query(
            runtime.base_dir,
            runtime.mdb_path,
            sql=sql,
            description=description or "",
            user_no=str(runtime.session.user_no or ""),
            code=code or "",
        )
        if err or rec is None:
            return None, err or "儲存失敗。"
        runtime.reload_metadata()
        return rec, None

    def run_query_export_xlsx(
        self,
        runtime: AppRuntime,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        filename_stem: str = "run_query",
    ) -> Tuple[bool, str, bytes]:
        from core.run_query_service import export_query_result_xlsx

        return export_query_result_xlsx(
            columns, rows, filename_stem=filename_stem or "run_query"
        )

    def run_query_saved_rows(
        self, runtime: AppRuntime, keyword: str = "", as_filter: bool = False
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        from core.run_query_service import (
            RUN_QUERY_TABLE,
            ensure_run_query_infra,
            resolve_run_query_data_path,
        )

        ok, err = ensure_run_query_infra(runtime.base_dir, runtime.mdb_path)
        if not ok:
            return None, err or "無法準備 RUN_QUERY。"
        path = resolve_run_query_data_path(runtime.base_dir)
        if not path or not os.path.isfile(path):
            return None, "找不到 USER_DATA。"
        backend = self._backend_for_path(runtime, path)
        try:
            runtime.data_dict.load_columns_for_dbf(RUN_QUERY_TABLE)
        except Exception:
            pass
        physical = backend.list_columns(RUN_QUERY_TABLE)
        if not physical:
            return None, "找不到 RUN_QUERY 資料表。"
        grid_fields = runtime.data_dict.grid_columns_for_table(RUN_QUERY_TABLE, physical)
        if not grid_fields:
            grid_fields = list(physical)
        physical_rows = backend.fetch_rows(
            RUN_QUERY_TABLE,
            keyword or "",
            bool(as_filter),
            limit=5000,
            column_order=physical,
        )
        grid_rows = self._map_rows_to_grid(grid_fields, physical, physical_rows)
        display_rows = self._format_rows_for_grid_display(
            runtime, RUN_QUERY_TABLE, grid_fields, grid_rows
        )
        return {
            "lookup_db": RUN_QUERY_TABLE,
            "fields": grid_fields,
            "physical_fields": physical,
            "columns": self._column_meta_dict(runtime, RUN_QUERY_TABLE, grid_fields),
            "rows": display_rows,
            "physical_rows": physical_rows,
            "total": len(grid_rows),
        }, None

    def _company_backend_for_runtime(self, runtime: AppRuntime) -> Optional[DbBackendBase]:
        co = str(getattr(runtime.session, "company_key", "") or "").strip() or "GS"
        path = resolve_company_db_path(runtime.base_dir, co)
        if not path or not os.path.exists(path):
            return None
        try:
            return self._backend_for_path(runtime, path)
        except Exception:
            return None

    def _append_related_match(
        self,
        matches: List[Dict[str, Any]],
        seen_tables: set,
        *,
        do_proc: str,
        title: str,
        table_name: str,
        total: int,
        preview: List[Dict[str, str]],
        details: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        if total <= 0:
            return
        key = (table_name or do_proc or title).strip().upper()
        detail_rows = list(details or [])
        if key and key in seen_tables:
            # 同表已有主檔命中時，改以交易筆數覆蓋較完整的摘要
            for m in matches:
                mk = str(m.get("table_name") or m.get("do_proc") or "").strip().upper()
                if mk == key:
                    if int(m.get("total") or 0) < total:
                        m["total"] = total
                        m["title"] = title or m.get("title")
                        m["preview"] = preview or m.get("preview") or []
                        m["do_proc"] = do_proc or m.get("do_proc")
                    if detail_rows:
                        m["details"] = detail_rows
                    elif preview and not m.get("details"):
                        # 保留較完整 preview 供後續載入明細
                        if len(preview) > len(m.get("preview") or []):
                            m["preview"] = preview
                    return
            return
        if key:
            seen_tables.add(key)
        matches.append(
            {
                "do_proc": do_proc,
                "title": title,
                "table_name": table_name,
                "total": total,
                "preview": preview,
                "details": detail_rows,
            }
        )

    @staticmethod
    def _related_detail_table_candidates(header_table: str) -> Tuple[str, ...]:
        h = (header_table or "").strip().upper()
        return {
            "INVOICE": ("INVSTK", "INV_ITEM"),
            "PURCHASE": ("PURSTK", "PUR_ITEM"),
            "QUOTATION": ("QUOTTRX", "QOUTTRX", "QUOSTK", "QTNSTK", "QUOTE_ITEM", "QUOT_ITEM"),
            "STKADJ": ("STKTRX", "STKADJ"),
            "TRANSFER": ("TRANTRX", "STKTRAN"),
            "INVSTK": ("INVSTK",),
            "PURSTK": ("PURSTK",),
            "QUOTTRX": ("QUOTTRX",),
        }.get(h, ())

    @staticmethod
    def _related_pick_col(cols: Sequence[str], names: Sequence[str]) -> str:
        want = {(n or "").strip().upper() for n in names}
        for c in cols:
            if (c or "").strip().upper() in want:
                return str(c)
        return ""

    @staticmethod
    def _related_cell(fields: Sequence[str], row: Sequence[str], names: Sequence[str]) -> str:
        idx = {str(f or "").strip().upper(): i for i, f in enumerate(fields)}
        for n in names:
            i = idx.get((n or "").strip().upper())
            if i is None or i >= len(row):
                continue
            v = str(row[i] if row[i] is not None else "").strip()
            if v:
                return v
        return ""

    def _load_related_tx_detail_lines(
        self,
        backend: DbBackendBase,
        header_table: str,
        tx_keys: Sequence[str],
        *,
        max_lines: int = 80,
    ) -> List[Dict[str, str]]:
        """依主檔交易編號載入明細列（數量／單價／金額）。"""
        from core.arap_settlement_service import _has_table
        from core.display_format import format_cell_display

        keys: List[str] = []
        seen_k = set()
        for k in tx_keys or []:
            kk = str(k or "").strip()
            if not kk:
                continue
            ku = kk.upper()
            if ku in seen_k:
                continue
            seen_k.add(ku)
            keys.append(kk)
        if not keys:
            return []

        header = (header_table or "").strip().upper()
        candidates = list(self._related_detail_table_candidates(header))
        if header and header not in {c.upper() for c in candidates}:
            # 若本身已是明細表
            if _has_table(backend, header_table):
                candidates = [header_table] + candidates

        out: List[Dict[str, str]] = []
        header_dates: Dict[str, str] = {}
        if header and _has_table(backend, header):
            try:
                from core.stock_query_service import _header_date_map

                header_dates = _header_date_map(backend, header) or {}
            except Exception:
                header_dates = {}

        for detail_table in candidates:
            tname = str(detail_table or "").strip()
            if not tname or not _has_table(backend, tname):
                continue
            try:
                cols = backend.list_columns(tname) or []
            except Exception:
                continue
            if not cols:
                continue
            key_col = self._related_pick_col(
                cols,
                (
                    "TX_KEY",
                    "TX_NO",
                    "QUOTE_NO",
                    "QUOTATION_NO",
                    "QUOT_NO",
                    "QUO_KEY",
                    "DOC_NO",
                    "ADJ_KEY",
                    "TRAN_KEY",
                ),
            )
            if not key_col:
                continue
            for tx_key in keys:
                if len(out) >= max_lines:
                    break
                sql = f"SELECT * FROM {tname} WHERE {key_col} = ?"
                try:
                    fields, rows = backend.fetch_rows_sql(
                        sql, params=[tx_key], limit=max(1, max_lines - len(out))
                    )
                except Exception:
                    continue
                if not fields:
                    fields = list(cols)
                for row in rows or []:
                    if len(out) >= max_lines:
                        break
                    date = self._related_cell(
                        fields, row, ("DATE", "TX_DATE", "DOC_DATE", "ADJ_DATE", "TRAN_DATE")
                    )
                    if date:
                        date = format_cell_display("DATE", date, "", "DATE")
                    elif header_dates:
                        date = header_dates.get(tx_key.strip().upper(), "")
                    qty = self._related_cell(
                        fields, row, ("QTY", "QUANTITY", "STK_QTY", "QUOT_QTY")
                    )
                    price = self._related_cell(
                        fields,
                        row,
                        ("UNIT_PRICE", "PRICE", "UPRICE", "UNITPRICE", "QUOT_PRICE"),
                    )
                    amt = self._related_cell(
                        fields,
                        row,
                        ("AMOUNT", "AMT", "NET_AMT", "TX_AMT", "LINE_AMT", "QUOT_AMT"),
                    )
                    if not amt and qty and price:
                        try:
                            from decimal import Decimal

                            amt = str(Decimal(str(qty).replace(",", "")) * Decimal(str(price).replace(",", "")))
                        except Exception:
                            amt = ""
                    if qty:
                        qty = format_cell_display("QTY", qty, "", "QTY") or qty
                    if price:
                        price = format_cell_display("UNIT_PRICE", price, "", "AMT") or price
                    if amt:
                        amt = format_cell_display("AMOUNT", amt, "", "AMT") or amt
                    out.append(
                        {
                            "TX_KEY": tx_key,
                            "DATE": date,
                            "STK_CODE": self._related_cell(
                                fields,
                                row,
                                ("STK_CODE", "STK_KEY", "STOCK_CODE", "ITEM_CODE", "STOCK_KEY"),
                            ),
                            "QTY": qty,
                            "UNIT_PRICE": price,
                            "AMOUNT": amt,
                            "UNIT": self._related_cell(
                                fields, row, ("UNIT", "UNIT_CODE", "UOM", "STK_UNIT")
                            ),
                            "DESC": self._related_cell(
                                fields,
                                row,
                                ("STK_DESC", "DESC", "DESCRIPTION", "ITEM_DESC", "REMARK"),
                            ),
                        }
                    )
            if out:
                break
        return out

    def _attach_related_tx_details(
        self, backend: DbBackendBase, matches: List[Dict[str, Any]]
    ) -> None:
        skip = {
            "STOCK",
            "CUSTVEND",
            "ACCOUNT",
            "PROGRAM",
            "COLUMNS",
            "MAINMENU",
            "USERS",
            "AI_COMMAND",
        }
        for m in matches:
            if m.get("details"):
                continue
            table = str(m.get("table_name") or m.get("do_proc") or "").strip()
            if not table or table.upper() in skip:
                continue
            keys: List[str] = []
            for p in m.get("preview") or []:
                if not isinstance(p, dict):
                    continue
                for kn in (
                    "TX_KEY",
                    "TX_NO",
                    "QUOTE_NO",
                    "QUOTATION_NO",
                    "QUOT_NO",
                    "VOU_KEY",
                    "DOC_NO",
                ):
                    v = str(p.get(kn) or "").strip()
                    if v:
                        keys.append(v)
                        break
            if not keys:
                continue
            details = self._load_related_tx_detail_lines(backend, table, keys)
            if details:
                m["details"] = details

    @staticmethod
    def _normalize_related_fields(
        fields: Optional[Sequence[str]] = None,
        *,
        include_date: Optional[bool] = None,
        include_qty: Optional[bool] = None,
    ) -> List[str]:
        default = ["date", "stk_code", "qty", "price", "amount"]
        if fields:
            out: List[str] = []
            for f in fields:
                fid = str(f or "").strip().lower()
                if not fid or fid in out:
                    continue
                # 相容舊別名
                alias = {
                    "stock": "stk_code",
                    "desc": "item",
                    "description": "item",
                    "unit_price": "price",
                    "amt": "amount",
                }.get(fid, fid)
                if alias not in out:
                    out.append(alias)
            fields_list = out
        else:
            fields_list = list(default)
        if include_date is False and "date" in fields_list:
            fields_list = [f for f in fields_list if f != "date"]
        if include_date is True and "date" not in fields_list:
            fields_list.insert(0, "date")
        if include_qty is False and "qty" in fields_list:
            fields_list = [f for f in fields_list if f != "qty"]
        if include_qty is True and "qty" not in fields_list:
            # 插在 stk_code / item / unit 之後
            insert_at = 0
            for i, f in enumerate(fields_list):
                if f in {"stk_code", "item", "unit", "date"}:
                    insert_at = i + 1
            fields_list.insert(insert_at, "qty")
        return fields_list

    @staticmethod
    def _related_detail_value(row: Dict[str, Any], field_id: str) -> str:
        mapping = {
            "date": ("DATE", "TX_DATE", "DOC_DATE"),
            "stk_code": ("STK_CODE", "STK_KEY", "ITEM_CODE"),
            "item": ("DESC", "ITEM", "STK_DESC", "DESCRIPTION", "ITEM_DESC"),
            "unit": ("UNIT", "UNIT_CODE", "UOM"),
            "qty": ("QTY", "QUANTITY"),
            "price": ("UNIT_PRICE", "PRICE"),
            "amount": ("AMOUNT", "AMT", "INV_AMT"),
        }
        for k in mapping.get(field_id, (field_id.upper(),)):
            v = str(row.get(k) or "").strip()
            if v:
                return v
        return ""

    @classmethod
    def _related_field_header(cls, field_id: str) -> str:
        return {
            "date": "日期",
            "stk_code": "貨品編號",
            "item": "項目",
            "unit": "單位",
            "qty": "數量",
            "price": "單價",
            "amount": "金額",
        }.get(field_id, field_id)

    @classmethod
    def _format_related_search_summary(
        cls,
        query: str,
        matches: List[Dict[str, Any]],
        *,
        scanned: int,
        timed_out: bool,
        max_scan: int,
        fields: Optional[Sequence[str]] = None,
        include_date: bool = True,
        include_qty: bool = True,
    ) -> str:
        field_ids = cls._normalize_related_fields(
            fields, include_date=include_date, include_qty=include_qty
        )
        date_keys = {"DATE", "TX_DATE", "DOC_DATE", "ADJ_DATE", "TRAN_DATE"}
        qty_keys = {"QTY", "QUANTITY", "STK_QTY", "QUOT_QTY"}
        price_keys = {"UNIT_PRICE", "PRICE", "UPRICE"}
        amount_keys = {"AMOUNT", "AMT", "INV_AMT", "NET_AMT"}
        item_keys = {"DESC", "ITEM", "STK_DESC", "DESCRIPTION", "ITEM_DESC"}
        unit_keys = {"UNIT", "UNIT_CODE", "UOM"}
        stk_keys = {"STK_CODE", "STK_KEY", "ITEM_CODE", "STOCK_CODE"}
        skip_preview_keys = set()
        if "date" not in field_ids:
            skip_preview_keys |= date_keys
        if "qty" not in field_ids:
            skip_preview_keys |= qty_keys
        if "price" not in field_ids:
            skip_preview_keys |= price_keys
        if "amount" not in field_ids:
            skip_preview_keys |= amount_keys
        if "item" not in field_ids:
            skip_preview_keys |= item_keys
        if "unit" not in field_ids:
            skip_preview_keys |= unit_keys
        if "stk_code" not in field_ids:
            skip_preview_keys |= stk_keys

        parts = [f"資料庫相關資料搜尋：關鍵字「{query}」"]
        total_rows = sum(int(m.get("total") or 0) for m in matches)
        parts.append(
            f"• 命中的作業／資料表：{len(matches)} 個；相關記錄：約 {total_rows} 筆"
        )
        if timed_out or scanned >= max_scan:
            parts.append(f"• 掃描範圍：{scanned} 個作業（已達上限，結果可能不完整）")
        for m in matches[:12]:
            title = str(m.get("title") or "")
            table = str(m.get("table_name") or m.get("do_proc") or "")
            total = m.get("total")
            parts.append(f"• {title}（{table}）：{total} 筆")
            details = [
                d for d in (m.get("details") or []) if isinstance(d, dict)
            ]
            if details:
                by_tx: Dict[str, List[Dict[str, str]]] = {}
                order: List[str] = []
                for d in details[:80]:
                    tx = str(d.get("TX_KEY") or "").strip() or "(無編號)"
                    if tx not in by_tx:
                        by_tx[tx] = []
                        order.append(tx)
                    by_tx[tx].append(d)
                for tx in order:
                    lines = by_tx[tx]
                    head = f"  － 交易編號 {tx}"
                    if "date" in field_ids:
                        date = cls._related_detail_value(lines[0] or {}, "date")
                        if date:
                            head += f"｜日期 {date}"
                    parts.append(head)
                    for ln in lines:
                        segs: List[str] = []
                        for fid in field_ids:
                            if fid == "date":
                                continue  # 已在交易標題
                            val = cls._related_detail_value(ln, fid)
                            if not val and fid not in {"qty", "price", "amount"}:
                                continue
                            if not val:
                                val = "-"
                            label = cls._related_field_header(fid)
                            if fid == "stk_code":
                                # 若未單獨要求項目，仍可把說明括在貨品後
                                item = cls._related_detail_value(ln, "item")
                                if "item" not in field_ids and item:
                                    segs.append(f"{label} {val}（{item}）")
                                else:
                                    segs.append(f"{label} {val}")
                            else:
                                segs.append(f"{label} {val}")
                        if segs:
                            parts.append("    · " + "｜".join(segs))
                continue
            preview = list(m.get("preview") or [])
            for p in preview[:12]:
                if not isinstance(p, dict):
                    continue
                bits = []
                for k, v in list(p.items())[:10]:
                    if not str(v).strip():
                        continue
                    ku = str(k).strip().upper()
                    if ku in skip_preview_keys:
                        continue
                    bits.append(f"{k}={v}")
                    if len(bits) >= 6:
                        break
                if bits:
                    parts.append("  － " + "｜".join(bits))
        return "\n".join(parts)

    def _enrich_related_by_stock(
        self,
        backend: DbBackendBase,
        query: str,
        matches: List[Dict[str, Any]],
        seen_tables: set,
    ) -> None:
        from core.stock_query_service import (
            find_stock_index,
            load_stock_transactions,
            load_stocks,
        )

        stocks, err = load_stocks(backend)
        if err or not stocks:
            return
        idx = find_stock_index(stocks, query)
        if idx < 0:
            return
        stock = stocks[idx]
        # 確保主檔也在結果中
        self._append_related_match(
            matches,
            seen_tables,
            do_proc="STOCK",
            title="存貨資料",
            table_name="STOCK",
            total=1,
            preview=[
                {
                    "STK_CODE": stock.key,
                    "CATE_CODE": stock.category,
                    "BRAND": stock.brand,
                    "MODEL": stock.model,
                    "STK_DESC": stock.desc,
                }
            ],
        )
        lines = load_stock_transactions(backend, stock.key)
        if not lines:
            return
        kind_meta = {
            "INV": ("銷貨／發票交易", "INVOICE", "INVSTK"),
            "PUR": ("購貨交易", "PURCHASE", "PURSTK"),
            "ADJ": ("存貨調整", "STKADJ", "STKTRX"),
            "TRI": ("存貨轉倉", "TRANSFER", "TRANTRX"),
        }
        grouped: Dict[str, List[Any]] = {}
        for ln in lines:
            kind = str(getattr(ln, "tx_category", "") or "").strip().upper() or "TX"
            grouped.setdefault(kind, []).append(ln)
        for kind, lns in grouped.items():
            title, header_table, detail_table = kind_meta.get(
                kind, (f"交易（{kind}）", kind, kind)
            )
            preview = []
            details = []
            for ln in lns[:50]:
                row = {
                    "TX_KEY": str(getattr(ln, "tx_key", "") or ""),
                    "DATE": str(getattr(ln, "date", "") or ""),
                    "QTY": str(getattr(ln, "qty", "") or ""),
                    "UNIT_PRICE": str(getattr(ln, "unit_price", "") or ""),
                    "AMOUNT": str(getattr(ln, "amount", "") or ""),
                    "STK_CODE": stock.key,
                    "UNIT": str(getattr(ln, "unit", "") or ""),
                    "DESC": str(getattr(stock, "desc", "") or ""),
                }
                preview.append(
                    {
                        "TX_KEY": row["TX_KEY"],
                        "DATE": row["DATE"],
                        "QTY": row["QTY"],
                        "AMOUNT": row["AMOUNT"],
                    }
                )
                details.append(row)
            self._append_related_match(
                matches,
                seen_tables,
                do_proc=header_table,
                title=title,
                table_name=header_table,
                total=len(lns),
                preview=preview[:8],
                details=details,
            )
            # 明細表名稱一併標註，避免與主檔混淆
            if detail_table and detail_table.upper() not in seen_tables:
                seen_tables.add(detail_table.upper())

    def _enrich_related_by_party(
        self,
        backend: DbBackendBase,
        query: str,
        matches: List[Dict[str, Any]],
        seen_tables: set,
    ) -> None:
        from core.party_query_service import (
            find_party_index,
            load_parties,
            load_party_transactions,
        )

        parties = []
        for mode, combined in (("AR", True), ("AP", False)):
            try:
                found, err = load_parties(backend, mode, combined=combined)
            except Exception:
                continue
            if err or not found:
                continue
            parties = found
            break
        if not parties:
            return
        idx = find_party_index(parties, query)
        if idx < 0:
            return
        party = parties[idx]
        self._append_related_match(
            matches,
            seen_tables,
            do_proc="CUSTVEND",
            title="顧客／供應商",
            table_name="CUSTVEND",
            total=1,
            preview=[
                {
                    "KEY": getattr(party, "key", "") or "",
                    "NAME": getattr(party, "name", "") or "",
                }
            ],
        )
        lines = []
        for mode in ("AR", "AP"):
            try:
                lines.extend(load_party_transactions(backend, mode, party.key) or [])
            except Exception:
                continue
        if not lines:
            return
        kind_meta = {
            "INV": ("發票交易", "INVOICE"),
            "REC": ("收款", "VOUCHER"),
            "PUR": ("採購交易", "PURCHASE"),
            "PAY": ("付款", "VOUCHER"),
        }
        grouped: Dict[str, List[Any]] = {}
        for ln in lines:
            kind = str(getattr(ln, "tx_category", "") or "").strip().upper() or "TX"
            grouped.setdefault(kind, []).append(ln)
        for kind, lns in grouped.items():
            title, table = kind_meta.get(kind, (f"往來交易（{kind}）", kind))
            preview = []
            for ln in lns[:50]:
                preview.append(
                    {
                        "TX_KEY": str(getattr(ln, "tx_key", "") or ""),
                        "DATE": str(getattr(ln, "date", "") or ""),
                        "INV_AMT": str(getattr(ln, "inv_amt", "") or ""),
                        "CURRENCY": str(getattr(ln, "currency", "") or ""),
                    }
                )
            self._append_related_match(
                matches,
                seen_tables,
                do_proc=table,
                title=title,
                table_name=table,
                total=len(lns),
                preview=preview,
            )

    def _scan_program_tx_tables(
        self,
        runtime: AppRuntime,
        backend: DbBackendBase,
        query: str,
        matches: List[Dict[str, Any]],
        seen_tables: set,
        *,
        time_budget_sec: float,
        started: float,
        max_tx_tables: int = 40,
    ) -> None:
        """掃描各作業 TX_FILE 明細表（例如 INVSTK），補主檔掃不到的交易。"""
        import time

        from core.stock_query_service import _stock_cols

        scanned_tx = 0
        for item in getattr(runtime.program_repo, "_items", None) or []:
            if time.monotonic() - started >= time_budget_sec:
                break
            if scanned_tx >= max_tx_tables:
                break
            do_proc = str(getattr(item, "do_proc", "") or "").strip()
            title = (
                str(getattr(item, "title", "") or "")
                or str(getattr(item, "chn_title", "") or "")
                or do_proc
            )
            tx_files = runtime.program_repo.list_tx_files_by_do_proc(do_proc)
            if not tx_files:
                raw = getattr(item, "tx_file", None)
                tx_files = self._parse_tx_files(raw)
            for tx_table in tx_files:
                if time.monotonic() - started >= time_budget_sec:
                    break
                tname = str(tx_table or "").strip()
                if not tname:
                    continue
                tkey = tname.upper()
                if tkey in seen_tables:
                    continue
                scanned_tx += 1
                try:
                    cols = backend.list_columns(tname)
                except Exception:
                    continue
                if not cols:
                    continue
                rows: List[List[str]] = []
                fields: List[str] = list(cols)
                # 優先用存貨欄精確查（A01 在 INVSTK.STK_CODE）
                stock_cols = _stock_cols(cols)
                if stock_cols:
                    where = " OR ".join(f"{c} = ?" for c in stock_cols)
                    sql = f"SELECT * FROM {tname} WHERE ({where})"
                    try:
                        fields, rows = backend.fetch_rows_sql(
                            sql, params=[query] * len(stock_cols), limit=50
                        )
                    except Exception:
                        rows = []
                if not rows:
                    try:
                        rows = backend.fetch_rows(
                            tname, query, True, limit=50, column_order=cols
                        )
                        fields = list(cols)
                    except Exception:
                        continue
                if not rows:
                    seen_tables.add(tkey)
                    continue
                preview = []
                details = []
                for row in rows[:40]:
                    row_map = {}
                    for i, name in enumerate(fields[:8]):
                        row_map[str(name)] = str(row[i]) if i < len(row) else ""
                    preview.append(row_map)
                    details.append(
                        {
                            "TX_KEY": self._related_cell(
                                fields,
                                row,
                                (
                                    "TX_KEY",
                                    "TX_NO",
                                    "QUOTE_NO",
                                    "QUOTATION_NO",
                                    "QUOT_NO",
                                    "DOC_NO",
                                ),
                            ),
                            "DATE": self._related_cell(
                                fields, row, ("DATE", "TX_DATE", "DOC_DATE")
                            ),
                            "STK_CODE": self._related_cell(
                                fields,
                                row,
                                ("STK_CODE", "STK_KEY", "STOCK_CODE", "ITEM_CODE"),
                            ),
                            "QTY": self._related_cell(
                                fields, row, ("QTY", "QUANTITY", "STK_QTY")
                            ),
                            "UNIT_PRICE": self._related_cell(
                                fields, row, ("UNIT_PRICE", "PRICE", "UPRICE")
                            ),
                            "AMOUNT": self._related_cell(
                                fields, row, ("AMOUNT", "AMT", "NET_AMT", "TX_AMT")
                            ),
                            "UNIT": self._related_cell(
                                fields, row, ("UNIT", "UNIT_CODE", "UOM", "STK_UNIT")
                            ),
                            "DESC": self._related_cell(
                                fields, row, ("STK_DESC", "DESC", "DESCRIPTION")
                            ),
                        }
                    )
                work = str(getattr(item, "work_file", "") or "").strip().upper()
                self._append_related_match(
                    matches,
                    seen_tables,
                    do_proc=do_proc or work or tname,
                    title=f"{title}（明細 {tname}）" if title else tname,
                    table_name=tname,
                    total=len(rows),
                    preview=preview[:8],
                    details=details,
                )

    def search_related_records(
        self,
        runtime: AppRuntime,
        keyword: str,
        *,
        max_matches: int = 20,
        max_scan: int = 120,
        time_budget_sec: float = 18.0,
        fields: Optional[Sequence[str]] = None,
        include_date: bool = True,
        include_qty: bool = True,
    ) -> Dict[str, Any]:
        """跨作業搜尋與關鍵字相關的資料（含主檔與交易明細）。"""
        import time

        query = (keyword or "").strip()
        if not query:
            return {"summary": "請提供要搜尋的編號或關鍵字。", "matches": [], "query": ""}
        if not getattr(runtime, "_program_loaded", False):
            runtime.reload_metadata()
        seen_procs = set()
        seen_tables: set = set()
        matches: List[Dict[str, Any]] = []
        scanned = 0
        started = time.monotonic()
        timed_out = False
        budget = max(3.0, float(time_budget_sec))

        for item in getattr(runtime.program_repo, "_items", None) or []:
            if time.monotonic() - started >= budget:
                timed_out = True
                break
            if scanned >= max(1, int(max_scan)):
                break
            do_proc = str(getattr(item, "do_proc", "") or "").strip()
            if not do_proc:
                continue
            key = do_proc.upper()
            if key in seen_procs:
                continue
            title_blob = " ".join(
                [
                    str(getattr(item, "title", "") or ""),
                    str(getattr(item, "other_title", "") or ""),
                    str(getattr(item, "chn_title", "") or ""),
                ]
            )
            work = str(getattr(item, "work_file", "") or "").strip().upper()
            if work in {"PROGRAM", "COLUMNS", "MAINMENU", "USERS", "AI_COMMAND"}:
                continue
            seen_procs.add(key)
            scanned += 1
            try:
                data, err = self.fetch_rows(
                    runtime, do_proc, query, as_filter=True, limit=50
                )
            except Exception:
                continue
            if err or not data:
                continue
            total = int(data.get("total") or 0)
            if total <= 0:
                continue
            fields = list(data.get("fields") or [])
            rows = list(data.get("rows") or [])
            preview = []
            for row in rows[:30]:
                row_map = {}
                for i, name in enumerate(fields[:8]):
                    row_map[str(name)] = str(row[i]) if i < len(row) else ""
                preview.append(row_map)
            self._append_related_match(
                matches,
                seen_tables,
                do_proc=do_proc,
                title=str(data.get("menu_title") or title_blob or do_proc),
                table_name=str(data.get("table_name") or work or ""),
                total=total,
                preview=preview,
            )
            if len(matches) >= max(1, int(max_matches)):
                break

        # 主檔掃完後：依編號補交易明細（STOCK→INVSTK/INVOICE 等）
        company_be = self._company_backend_for_runtime(runtime)
        if company_be is not None and time.monotonic() - started < budget:
            try:
                company_be.refresh_for_read()
            except Exception:
                pass
            try:
                self._enrich_related_by_stock(company_be, query, matches, seen_tables)
            except Exception:
                pass
            try:
                self._enrich_related_by_party(company_be, query, matches, seen_tables)
            except Exception:
                pass
            try:
                self._scan_program_tx_tables(
                    runtime,
                    company_be,
                    query,
                    matches,
                    seen_tables,
                    time_budget_sec=budget,
                    started=started,
                )
            except Exception:
                pass
            try:
                self._attach_related_tx_details(company_be, matches)
            except Exception:
                pass

        if not matches:
            note = f"（已掃描 {scanned} 個作業"
            if timed_out:
                note += "，已達時間上限"
            note += "）"
            return {
                "summary": f"找不到與「{query}」相關的資料。{note}",
                "matches": [],
                "query": query,
                "scanned": scanned,
                "timed_out": timed_out,
            }
        field_ids = self._normalize_related_fields(
            fields, include_date=include_date, include_qty=include_qty
        )
        return {
            "summary": self._format_related_search_summary(
                query,
                matches,
                scanned=scanned,
                timed_out=timed_out,
                max_scan=max_scan,
                fields=field_ids,
                include_date=("date" in field_ids),
                include_qty=("qty" in field_ids),
            ),
            "matches": matches,
            "query": query,
            "scanned": scanned,
            "timed_out": timed_out,
            "fields": field_ids,
            "include_date": "date" in field_ids,
            "include_qty": "qty" in field_ids,
        }

    def export_related_records_xlsx(
        self,
        runtime: AppRuntime,
        keyword: str,
        *,
        fields: Optional[Sequence[str]] = None,
        include_date: bool = True,
        include_qty: bool = True,
    ) -> Tuple[bool, str, bytes]:
        """將 AI 相關資料搜尋結果匯出為 XLSX。"""
        query = (keyword or "").strip()
        if not query:
            return False, "請提供要匯出的編號或關鍵字。", b""
        field_ids = self._normalize_related_fields(
            fields, include_date=include_date, include_qty=include_qty
        )
        data = self.search_related_records(
            runtime,
            query,
            fields=field_ids,
            include_date=("date" in field_ids),
            include_qty=("qty" in field_ids),
        )
        matches = [m for m in (data.get("matches") or []) if isinstance(m, dict)]
        if not matches:
            return False, str(data.get("summary") or "找不到可匯出的資料。"), b""
        try:
            from openpyxl import Workbook
        except Exception as ex:
            return False, f"無法載入 Excel 匯出元件：{ex}", b""

        wb = Workbook()
        ws = wb.active
        ws.title = "RelatedData"
        headers = ["類別", "資料表", "交易編號"] + [
            self._related_field_header(fid) for fid in field_ids
        ]
        ws.append(headers)
        for m in matches:
            title = str(m.get("title") or "")
            table = str(m.get("table_name") or m.get("do_proc") or "")
            details = [d for d in (m.get("details") or []) if isinstance(d, dict)]
            if details:
                for d in details:
                    row = [title, table, str(d.get("TX_KEY") or "")]
                    for fid in field_ids:
                        row.append(self._related_detail_value(d, fid))
                    ws.append(row)
                continue
            previews = [p for p in (m.get("preview") or []) if isinstance(p, dict)]
            if not previews:
                ws.append(
                    [title, table, ""] + ["" for _ in field_ids]
                )
                continue
            for p in previews:
                row = [
                    title,
                    table,
                    str(
                        p.get("TX_KEY")
                        or p.get("TX_NO")
                        or p.get("QUOTE_NO")
                        or p.get("VOU_KEY")
                        or ""
                    ),
                ]
                for fid in field_ids:
                    row.append(self._related_detail_value(p, fid))
                ws.append(row)
        for col in ws.columns:
            letter = col[0].column_letter
            max_len = max(len(str(c.value or "")) for c in col)
            ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 28)
        bio = io.BytesIO()
        wb.save(bio)
        return True, f"related_{query}.xlsx", bio.getvalue()

    def save_ai_command_chat(
        self,
        runtime: AppRuntime,
        messages: List[Dict[str, str]],
        title: str = "",
        prompt: str = "",
        reply: str = "",
    ) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        """將目前指令寫入 AI_COMMAND。"""
        from core.ai_command_service import save_ai_command

        rec, err = save_ai_command(
            runtime.base_dir,
            runtime.mdb_path,
            user_no=str(runtime.session.user_no or ""),
            messages=messages,
            prompt=prompt or "",
            reply=reply or "",
            title=title or "",
            lang=runtime.lang,
        )
        if err or rec is None:
            return None, err or "儲存失敗。"
        # 若首次建立 PROGRAM／COLUMNS，重載以便隨後開 GRID
        runtime.reload_metadata()
        return rec, None

    def get_form_values(
        self,
        runtime: AppRuntime,
        do_proc: str,
        physical_row: List[str],
    ) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        return self._form_values_from_row(
            runtime,
            schema.table_name,
            schema.form_fields,
            schema.physical_fields,
            physical_row,
        ), None

    def fetch_tx_rows(
        self,
        runtime: AppRuntime,
        do_proc: str,
        tx_table: str,
        master_row: List[str],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        physical = backend.list_columns(tx_table)
        if not physical:
            physical = ["LINE_NO", "ITEM_CODE", "QTY", "PRICE", "AMOUNT"]
        grid_fields = runtime.data_dict.grid_columns_for_table(tx_table, physical)
        if not grid_fields:
            grid_fields = runtime.data_dict.edit_columns_for_table(tx_table, physical)
        if not grid_fields:
            grid_fields = list(physical)
        key_col, key_val = self._resolve_master_tx_key(runtime, schema, master_row)

        rows: List[List[str]] = []
        if key_col and key_val:
            rows = backend.fetch_rows_where(
                tx_table, key_col, key_val, limit=200, column_order=physical
            )
            be = str(getattr(backend, "last_error", "") or "").strip()
            if be:
                return None, f"讀取明細「{tx_table}」失敗：{be}"
        grid_rows = self._map_rows_to_grid(grid_fields, physical, rows)
        display_rows = self._format_rows_for_grid_display(
            runtime, tx_table, grid_fields, grid_rows
        )
        return {
            "tx_table": tx_table,
            "fields": grid_fields,
            "physical_fields": physical,
            "columns": self._column_meta_dict(runtime, tx_table, grid_fields),
            "rows": display_rows,
            "physical_rows": [list(r) for r in rows],
            "read_only": False,
            "filter_column": key_col,
            "filter_value": key_val,
        }, None

    @staticmethod
    def _resolve_tx_filter_column(
        tx_physical: List[str],
        master_key_col: Optional[str],
    ) -> Optional[str]:
        if master_key_col:
            want = master_key_col.strip().upper()
            for c in tx_physical:
                if c.strip().upper() == want:
                    return c
        for c in tx_physical:
            if c.strip().upper() == "TX_KEY":
                return c
        return None

    def _resolve_master_tx_key_from_form(
        self,
        runtime: AppRuntime,
        schema: WorkSchema,
        form_values: Dict[str, str],
        master_row: List[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        if schema.print_doc_key_column:
            pk = schema.print_doc_key_column
            if pk in form_values and (form_values.get(pk) or "").strip():
                return pk, form_values[pk].strip()
            try:
                idx = schema.physical_fields.index(pk)
                if idx < len(master_row) and (master_row[idx] or "").strip():
                    return pk, master_row[idx].strip()
            except ValueError:
                pass
        for f in schema.form_fields:
            if f.strip().upper() == "TX_KEY":
                v = (form_values.get(f) or "").strip()
                if v:
                    return f, v
                try:
                    idx = schema.physical_fields.index(f)
                    if idx < len(master_row) and (master_row[idx] or "").strip():
                        return f, master_row[idx].strip()
                except ValueError:
                    pass
        return self._resolve_master_tx_key(runtime, schema, master_row)

    def save_tx_rows(
        self,
        runtime: AppRuntime,
        do_proc: str,
        tx_table: str,
        physical_rows: List[List[str]],
        master_form_values: Dict[str, str],
        master_row: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """與 TxDetailGridPane.save_to_backend 相同：刪除同鍵舊明細後整批重寫。"""
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return False, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        physical = backend.list_columns(tx_table)
        if not physical:
            physical = ["LINE_NO", "ITEM_CODE", "QTY", "PRICE", "AMOUNT"]

        master_row = list(master_row or [])
        master_key_col, master_key_val = self._resolve_master_tx_key_from_form(
            runtime, schema, master_form_values, master_row
        )
        key_col = self._resolve_tx_filter_column(physical, master_key_col)

        if master_key_val and not key_col:
            return False, f"{tx_table}: 找不到 TX 鍵欄位。"

        key_value = master_key_val
        if key_col and key_value is not None:
            key_fmt = runtime.data_dict.get_data_format(tx_table, key_col)
            key_typ = runtime.data_dict.get_data_type(tx_table, key_col)
            key_value = normalize_storage_value(key_col, key_fmt, key_value, key_typ)

        if key_value and key_col:
            existing = backend.fetch_rows_where(
                tx_table, key_col, key_value, limit=500, column_order=physical
            )
            if existing:
                if not backend.delete_one(tx_table, [key_col], [key_value]):
                    be = getattr(backend, "last_error", "") or ""
                    return False, be or f"{tx_table}: 刪除舊明細失敗。"

        auto_like = {"ID", "AUTOID", "AUTO_ID", "RECNO", "REC_NO"}
        string_types = {"S", "STRING", "STR", "TEXT", "CHAR", "VARCHAR", "NVARCHAR"}
        key_idx = None
        if key_col:
            for i, c in enumerate(physical):
                if c.strip().upper() == key_col.strip().upper():
                    key_idx = i
                    break

        # 依目前列順序重算 ITEM_NO，再寫入
        rows_to_save: List[List[str]] = []
        for src in physical_rows:
            row = list(src[: len(physical)])
            while len(row) < len(physical):
                row.append("")
            if key_idx is not None and key_value is not None:
                row[key_idx] = key_value
            meaningful = False
            for i, v in enumerate(row):
                if key_idx is not None and i == key_idx:
                    continue
                if str(v or "").strip():
                    meaningful = True
                    break
            if meaningful:
                rows_to_save.append(row)
        renumber_item_no(physical, rows_to_save)

        for row in rows_to_save:
            insert_fields: List[str] = []
            insert_values: List[str] = []
            for i, col in enumerate(physical):
                col_up = col.strip().upper()
                if key_idx is not None and i == key_idx and key_value is not None:
                    insert_fields.append(col)
                    insert_values.append(key_value)
                    continue
                if col_up in auto_like:
                    continue
                raw = row[i] if i < len(row) else ""
                txt = str(raw).strip()
                if not txt:
                    dtyp = runtime.data_dict.get_data_type(tx_table, col).strip().upper()
                    if dtyp not in string_types:
                        continue
                fmt = runtime.data_dict.get_data_format(tx_table, col)
                dtyp = runtime.data_dict.get_data_type(tx_table, col)
                norm = normalize_storage_value(col, fmt, str(raw), dtyp)
                insert_fields.append(col)
                insert_values.append(norm)

            if not insert_fields:
                continue
            if not backend.insert_one(tx_table, insert_fields, insert_values):
                be = getattr(backend, "last_error", "") or ""
                return False, be or f"{tx_table}: 寫入明細失敗。"
        return True, None

    def resolve_attachments(
        self,
        runtime: AppRuntime,
        do_proc: str,
        old_row: List[str],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """與 WorkPage._on_attachment 相同邏輯，回傳 Web 可用的附件清單。"""
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        if not old_row:
            return None, "請先選取一筆記錄。"
        key_code = schema.print_doc_key_column or ""
        lookup_col, key_value, folder, files = resolve_attachments_for_row(
            schema.work_actions.attach_path,
            schema.work_actions.attach_key,
            key_code,
            schema.physical_fields,
            old_row,
            co_key=runtime.session.company_key,
            do_proc=do_proc,
            table_name=schema.table_name,
            app_base_dir=runtime.base_dir,
        )
        if not lookup_col:
            return None, "未設定 ATTACH_KEY 或 KEY_CODE 欄位。"
        if not key_value:
            return None, f"目前記錄的「{lookup_col}」為空白，無法搜尋附件。"
        file_items = []
        for fp in files:
            name = os.path.basename(fp)
            kind = "pdf" if is_pdf_path(fp) else "image" if is_image_path(fp) else "other"
            file_items.append({"path": fp, "name": name, "kind": kind})
        show_folder = user_may_see_attach_folder(runtime.session.group_level)
        folder_missing = bool(folder) and not os.path.isdir(folder)
        return {
            "lookup_column": lookup_col,
            "key_value": key_value,
            "folder": folder if show_folder else "",
            "files": file_items,
            "show_attach_folder": show_folder,
            "not_found_message": format_attach_not_found_message(
                runtime.lang,
                key_value,
                folder,
                runtime.session.group_level,
                folder_missing=folder_missing,
            ),
        }, None

    @staticmethod
    def _settlement_line_dict(ln: SettlementLine) -> Dict[str, Any]:
        return {
            "tx_key": ln.tx_key,
            "inv_no": ln.inv_no,
            "date": ln.date,
            "currency": ln.currency,
            "rate": ln.rate,
            "net_amt": ln.net_amt,
            "paid_amt": ln.paid_amt,
            "balance": ln.balance,
            "pay_amount": ln.pay_amount,
            "discount": ln.discount,
            "in_trx": ln.in_trx,
            "old_pay_amount": ln.old_pay_amount,
            "old_discount": ln.old_discount,
        }

    @staticmethod
    def _settlement_line_from_dict(d: Dict[str, Any]) -> SettlementLine:
        return SettlementLine(
            tx_key=str(d.get("tx_key") or ""),
            inv_no=str(d.get("inv_no") or ""),
            date=str(d.get("date") or ""),
            currency=str(d.get("currency") or ""),
            rate=str(d.get("rate") or ""),
            net_amt=str(d.get("net_amt") or ""),
            paid_amt=str(d.get("paid_amt") or ""),
            balance=str(d.get("balance") or ""),
            pay_amount=str(d.get("pay_amount") or ""),
            discount=str(d.get("discount") or ""),
            in_trx=bool(d.get("in_trx")),
            old_pay_amount=str(d.get("old_pay_amount") or ""),
            old_discount=str(d.get("old_discount") or ""),
        )

    @classmethod
    def _settlement_doc_dict(cls, doc: SettlementDocument) -> Dict[str, Any]:
        h = doc.header
        return {
            "mode": doc.mode,
            "header": {
                "vou_key": h.vou_key,
                "settle_date": h.settle_date,
                "party_key": h.party_key,
                "party_name": h.party_name,
                "settle_amount": h.settle_amount,
                "exchange_diff": h.exchange_diff,
            },
            "lines": [cls._settlement_line_dict(ln) for ln in doc.lines],
        }

    @classmethod
    def _settlement_doc_from_dict(cls, data: Dict[str, Any]) -> SettlementDocument:
        hdr = data.get("header") or {}
        header = SettlementHeader(
            vou_key=str(hdr.get("vou_key") or ""),
            settle_date=str(hdr.get("settle_date") or ""),
            party_key=str(hdr.get("party_key") or ""),
            party_name=str(hdr.get("party_name") or ""),
            settle_amount=str(hdr.get("settle_amount") or ""),
            exchange_diff=str(hdr.get("exchange_diff") or ""),
        )
        lines = [
            cls._settlement_line_from_dict(x)
            for x in (data.get("lines") or [])
        ]
        mode = data.get("mode") or "AR"
        return SettlementDocument(mode=mode, header=header, lines=lines)

    @staticmethod
    def _settlement_totals_dict(doc: SettlementDocument) -> Dict[str, str]:
        bal, pay, disc = sum_totals(doc.lines)
        exch = doc.header.exchange_diff or "0"
        from decimal import Decimal

        rem = remaining_settlement(
            Decimal(str(doc.header.settle_amount or "0").replace(",", "")),
            pay,
            disc,
            Decimal(str(exch or "0").replace(",", "")),
        )
        return {
            "total_balance": format(bal, "f"),
            "total_pay": format(pay, "f"),
            "total_discount": format(disc, "f"),
            "remaining": format(rem, "f"),
        }

    @staticmethod
    def _party_info_dict(p: PartyInfo) -> Dict[str, str]:
        return {
            "key": p.key,
            "name": p.name,
            "contact": p.contact,
            "tel": p.tel,
            "mobile": p.mobile,
            "credit_limit": getattr(p, "credit_limit", "") or "",
            "remain_credit": getattr(p, "remain_credit", "") or "",
        }

    @staticmethod
    def _party_line_dict(ln: PartyQueryLine) -> Dict[str, str]:
        return {
            "date": ln.date,
            "tx_category": ln.tx_category,
            "tx_key": ln.tx_key,
            "currency": ln.currency,
            "rate": ln.rate,
            "inv_amt": ln.inv_amt,
            "paid_amt": ln.paid_amt,
            "recv_amt": ln.recv_amt,
            "settle_amt": ln.settle_amt,
        }

    @classmethod
    def _party_query_payload(
        cls, doc: PartyQueryDocument, lang: LanguageCode
    ) -> Dict[str, Any]:
        party = current_party(doc)
        return {
            "mode": doc.mode,
            "parties": [cls._party_info_dict(p) for p in doc.parties],
            "party_index": doc.party_index,
            "party": cls._party_info_dict(party),
            "lines": [cls._party_line_dict(ln) for ln in doc.lines],
            "totals": party_totals_dict(doc.lines),
            "date_from": doc.date_from,
            "date_to": doc.date_to,
            "tx_kinds": list(getattr(doc, "tx_kinds", None) or list(TX_KIND_OPTIONS)),
            "tx_kind": (
                "ALL"
                if set(getattr(doc, "tx_kinds", None) or []) >= set(TX_KIND_OPTIONS)
                else ((getattr(doc, "tx_kinds", None) or ["ALL"])[0] if getattr(doc, "tx_kinds", None) else "ALL")
            ),
            "lang": lang,
        }

    def load_party_query(
        self,
        runtime: AppRuntime,
        do_proc: str,
        old_row: List[str],
        *,
        party_index: int = -1,
        date_from: str = "",
        date_to: str = "",
        tx_kinds: Optional[List[str]] = None,
        tx_kind: str = "ALL",
        party_key: str = "",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        other_title = schema.work_actions.other_title or ""
        if not is_party_query_program(do_proc, schema.table_name, other_title):
            return None, "此作業非顧客／供應商查詢。"
        backend = self._backend_for_path(runtime, schema.db_path)
        doc, load_err = load_party_query(
            backend,
            do_proc,
            old_row,
            schema.physical_fields,
            table_name=schema.table_name,
            other_title=other_title,
            party_index=party_index,
            date_from=date_from,
            date_to=date_to,
            tx_kinds=tx_kinds,
            tx_kind=tx_kind if tx_kinds is None else "",
            party_key=party_key,
        )
        if load_err or doc is None:
            return None, load_err or "無法載入查詢資料。"
        return self._party_query_payload(doc, runtime.lang), None

    def filter_party_query_lines(
        self,
        lines: List[Dict[str, Any]],
        keyword: str,
        *,
        as_filter: bool = False,
    ) -> Dict[str, Any]:
        parsed = [
            PartyQueryLine(
                date=str(x.get("date") or ""),
                tx_category=str(x.get("tx_category") or ""),
                tx_key=str(x.get("tx_key") or ""),
                currency=str(x.get("currency") or ""),
                rate=str(x.get("rate") or ""),
                inv_amt=str(x.get("inv_amt") or ""),
                paid_amt=str(x.get("paid_amt") or ""),
                recv_amt=str(x.get("recv_amt") or ""),
                settle_amt=str(x.get("settle_amt") or ""),
            )
            for x in lines
        ]
        if as_filter:
            filtered = filter_party_lines(parsed, keyword)
            out_lines = filtered
            selected_index = None
        else:
            idx = find_party_line_index(parsed, keyword)
            out_lines = parsed
            selected_index = idx
        return {
            "lines": [self._party_line_dict(ln) for ln in out_lines],
            "totals": party_totals_dict(out_lines),
            "selected_index": selected_index,
        }

    @staticmethod
    def _stock_info_dict(s: StockInfo) -> Dict[str, str]:
        return {
            "key": s.key,
            "category": s.category,
            "brand": s.brand,
            "model": s.model,
            "desc": s.desc,
        }

    @staticmethod
    def _stock_line_dict(ln: StockQueryLine) -> Dict[str, str]:
        return {
            "date": ln.date,
            "tx_category": ln.tx_category,
            "tx_key": ln.tx_key,
            "qty": ln.qty,
            "unit": ln.unit,
            "weight": ln.weight,
            "wgt_unit": ln.wgt_unit,
            "warehouse": ln.warehouse,
            "unit_price": ln.unit_price,
            "amount": ln.amount,
            "unit_cost": ln.unit_cost,
            "cost_amt": ln.cost_amt,
        }

    @classmethod
    def _stock_query_payload(
        cls, doc: StockQueryDocument, lang: LanguageCode
    ) -> Dict[str, Any]:
        stock = current_stock(doc)
        return {
            "stocks": [cls._stock_info_dict(s) for s in doc.stocks],
            "stock_index": doc.stock_index,
            "stock": cls._stock_info_dict(stock),
            "lines": [cls._stock_line_dict(ln) for ln in doc.lines],
            "totals": stock_totals_dict(doc.lines),
            "date_from": doc.date_from,
            "date_to": doc.date_to,
            "tx_kinds": list(getattr(doc, "tx_kinds", None) or list(STOCK_TX_KIND_OPTIONS)),
            "lang": lang,
        }

    def load_stock_query(
        self,
        runtime: AppRuntime,
        do_proc: str,
        old_row: List[str],
        *,
        stock_index: int = -1,
        date_from: str = "",
        date_to: str = "",
        tx_kinds: Optional[List[str]] = None,
        stock_key: str = "",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        other_title = schema.work_actions.other_title or ""
        if not is_stock_query_program(do_proc, schema.table_name, other_title):
            if (schema.table_name or "").strip().upper() != "STOCK":
                return None, "此作業非存貨查詢。"
        backend = self._backend_for_path(runtime, schema.db_path)
        doc, load_err = load_stock_query(
            backend,
            do_proc,
            old_row,
            schema.physical_fields,
            table_name=schema.table_name,
            other_title=other_title or "存貨查詢",
            stock_index=stock_index,
            date_from=date_from,
            date_to=date_to,
            tx_kinds=tx_kinds,
            stock_key=stock_key,
        )
        if load_err or doc is None:
            return None, load_err or "無法載入查詢資料。"
        return self._stock_query_payload(doc, runtime.lang), None

    def filter_stock_query_lines(
        self,
        lines: List[Dict[str, Any]],
        keyword: str,
        *,
        as_filter: bool = False,
    ) -> Dict[str, Any]:
        parsed = [
            StockQueryLine(
                date=str(x.get("date") or ""),
                tx_category=str(x.get("tx_category") or ""),
                tx_key=str(x.get("tx_key") or ""),
                qty=str(x.get("qty") or ""),
                unit=str(x.get("unit") or ""),
                weight=str(x.get("weight") or ""),
                wgt_unit=str(x.get("wgt_unit") or ""),
                warehouse=str(x.get("warehouse") or ""),
                unit_price=str(x.get("unit_price") or ""),
                amount=str(x.get("amount") or ""),
                unit_cost=str(x.get("unit_cost") or ""),
                cost_amt=str(x.get("cost_amt") or ""),
            )
            for x in lines
        ]
        if as_filter:
            filtered = filter_stock_lines(parsed, keyword)
            out_lines = filtered
            selected_index = None
        else:
            idx = find_stock_line_index(parsed, keyword)
            out_lines = parsed
            selected_index = idx
        return {
            "lines": [self._stock_line_dict(ln) for ln in out_lines],
            "totals": stock_totals_dict(out_lines),
            "selected_index": selected_index,
        }

    @staticmethod
    def _account_info_dict(a: AccountInfo) -> Dict[str, str]:
        return {
            "key": a.key,
            "parent_key": a.parent_key,
            "acc_type": a.acc_type,
            "acc_level": a.acc_level,
            "name": a.name,
        }

    @staticmethod
    def _account_line_dict(ln: AccountQueryLine) -> Dict[str, str]:
        return {
            "date": ln.date,
            "vou_key": ln.vou_key,
            "currency": ln.currency,
            "rate": ln.rate,
            "dr_amt": ln.dr_amt,
            "cr_amt": ln.cr_amt,
            "remark": ln.remark,
        }

    @classmethod
    def _account_query_payload(
        cls, doc: AccountQueryDocument, lang: LanguageCode
    ) -> Dict[str, Any]:
        account = current_account(doc)
        return {
            "accounts": [cls._account_info_dict(a) for a in doc.accounts],
            "account_index": doc.account_index,
            "account": cls._account_info_dict(account),
            "lines": [cls._account_line_dict(ln) for ln in doc.lines],
            "totals": account_totals_dict(doc.lines),
            "date_from": doc.date_from,
            "date_to": doc.date_to,
            "tx_kinds": list(
                getattr(doc, "tx_kinds", None) or list(ACCOUNT_TX_KIND_OPTIONS)
            ),
            "lang": lang,
        }

    def load_account_query(
        self,
        runtime: AppRuntime,
        do_proc: str,
        old_row: List[str],
        *,
        account_index: int = -1,
        account_key: str = "",
        date_from: str = "",
        date_to: str = "",
        tx_kinds: Optional[List[str]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        other_title = schema.work_actions.other_title or ""
        if not is_account_query_program(do_proc, schema.table_name, other_title):
            if (schema.table_name or "").strip().upper() != "ACCOUNT":
                return None, "此作業非賬戶查詢。"
        backend = self._backend_for_path(runtime, schema.db_path)
        doc, load_err = load_account_query(
            backend,
            do_proc,
            old_row,
            schema.physical_fields,
            table_name=schema.table_name,
            other_title=other_title or "賬戶查詢",
            account_index=account_index,
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            tx_kinds=tx_kinds,
        )
        if load_err or doc is None:
            return None, load_err or "無法載入查詢資料。"
        return self._account_query_payload(doc, runtime.lang), None

    def filter_account_query_lines(
        self,
        lines: List[Dict[str, Any]],
        keyword: str,
        *,
        as_filter: bool = False,
    ) -> Dict[str, Any]:
        parsed = [
            AccountQueryLine(
                date=str(x.get("date") or ""),
                vou_key=str(x.get("vou_key") or ""),
                currency=str(x.get("currency") or ""),
                rate=str(x.get("rate") or ""),
                dr_amt=str(x.get("dr_amt") or ""),
                cr_amt=str(x.get("cr_amt") or ""),
                remark=str(x.get("remark") or ""),
            )
            for x in lines
        ]
        if as_filter:
            filtered = filter_account_lines(parsed, keyword)
            out_lines = filtered
            selected_index = None
        else:
            idx = find_account_line_index(parsed, keyword)
            out_lines = parsed
            selected_index = idx
        return {
            "lines": [self._account_line_dict(ln) for ln in out_lines],
            "totals": account_totals_dict(out_lines),
            "selected_index": selected_index,
        }

    def load_receipt_payment(
        self,
        runtime: AppRuntime,
        do_proc: str,
        old_row: List[str],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        if not old_row:
            return None, "請先選取一筆記錄。"
        other_title = schema.work_actions.other_title or ""
        if not is_receipt_payment_program(do_proc, schema.table_name, other_title):
            return None, "此作業非收款或付款。"
        backend = self._backend_for_path(runtime, schema.db_path)
        login_date = str(getattr(runtime.session, "login_date", "") or "").strip()
        doc, load_err = load_receipt_payment(
            backend,
            old_row,
            schema.physical_fields,
            table_name=schema.table_name,
            other_title=other_title,
            login_date=login_date,
        )
        if load_err or doc is None:
            return None, load_err or "無法載入收付款資料。"
        payload = receipt_payment_to_dict(doc)
        payload["lang"] = runtime.lang
        payload["other_title"] = other_title
        return payload, None

    def save_receipt_payment(
        self,
        runtime: AppRuntime,
        do_proc: str,
        document: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], str]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return False, err or "無法解析作業。", ""
        other_title = schema.work_actions.other_title or ""
        if not is_receipt_payment_program(do_proc, schema.table_name, other_title):
            return False, "此作業非收款或付款。", ""
        backend = self._backend_for_path(runtime, schema.db_path)
        doc = receipt_payment_from_dict(document or {})
        return save_receipt_payment(backend, doc)

    def load_arap_settlement(
        self,
        runtime: AppRuntime,
        do_proc: str,
        old_row: List[str],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return None, err or "無法解析作業。"
        if not old_row:
            return None, "請先選取一筆傳票記錄。"
        other_title = schema.work_actions.other_title or ""
        if not is_arap_settlement_program(do_proc, schema.table_name, other_title):
            return None, "此作業非應收應付清賬。"
        backend = self._backend_for_path(runtime, schema.db_path)
        doc, load_err = load_settlement(
            backend,
            do_proc,
            old_row,
            schema.physical_fields,
            table_name=schema.table_name,
            other_title=other_title,
        )
        if load_err or doc is None:
            return None, load_err or "無法載入清賬資料。"
        payload = self._settlement_doc_dict(doc)
        payload["totals"] = self._settlement_totals_dict(doc)
        payload["lang"] = runtime.lang
        return payload, None

    def save_arap_settlement(
        self,
        runtime: AppRuntime,
        do_proc: str,
        document: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        schema, err = self.resolve_work(runtime, do_proc, reload_program=False)
        if err or schema is None:
            return False, err or "無法解析作業。"
        backend = self._backend_for_path(runtime, schema.db_path)
        doc = self._settlement_doc_from_dict(document)
        return save_settlement(backend, doc)

    def auto_arap_settlement(
        self,
        document: Dict[str, Any],
    ) -> Dict[str, Any]:
        doc = self._settlement_doc_from_dict(document)
        auto_settle_lines(
            doc.lines,
            doc.header.settle_amount,
            doc.header.exchange_diff,
        )
        payload = self._settlement_doc_dict(doc)
        payload["totals"] = self._settlement_totals_dict(doc)
        return payload

    def filter_arap_lines(
        self,
        document: Dict[str, Any],
        keyword: str,
        *,
        as_filter: bool = False,
    ) -> Dict[str, Any]:
        doc = self._settlement_doc_from_dict(document)
        if as_filter:
            lines = filter_lines(doc.lines, keyword)
        else:
            idx = find_line_index(doc.lines, keyword)
            lines = list(doc.lines)
            payload = self._settlement_doc_dict(doc)
            payload["selected_index"] = idx
            payload["totals"] = self._settlement_totals_dict(doc)
            return payload
        doc.lines = lines
        payload = self._settlement_doc_dict(doc)
        payload["totals"] = self._settlement_totals_dict(doc)
        return payload

    def data_import_kinds(
        self, runtime: AppRuntime, do_proc: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not is_data_import_program(do_proc):
            return None, "此作業非資料匯入 (DATAIMPORT / DO_DATAIMPORT)。"
        _, err = self._ensure_allowed_program(runtime, do_proc)
        if err:
            return None, err
        from core.db_factory import (
            resolve_default_transfer_folder,
            resolve_transfer_db_path,
        )

        default_folder, default_note = resolve_default_transfer_folder(runtime.base_dir)
        default_transfer = resolve_transfer_db_path(
            runtime.base_dir, folder=default_folder
        )
        return {
            "kinds": list_import_kind_options(),
            "default_folder": default_folder,
            "default_transfer_path": default_transfer
            if os.path.isfile(default_transfer)
            else "",
            "default_note": default_note or "",
        }, None

    def data_import_folders(
        self, runtime: AppRuntime, do_proc: str, path: str = ""
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not is_data_import_program(do_proc):
            return None, "此作業非資料匯入 (DATAIMPORT / DO_DATAIMPORT)。"
        _, err = self._ensure_allowed_program(runtime, do_proc)
        if err:
            return None, err
        data, list_err = list_import_source_folders(runtime.base_dir, path=path or "")
        if list_err:
            return None, list_err
        return data, None

    def data_import_pending(
        self, runtime: AppRuntime, do_proc: str, kind: str, folder: str = ""
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not is_data_import_program(do_proc):
            return None, "此作業非資料匯入 (DATAIMPORT / DO_DATAIMPORT)。"
        # 直接解析真實路徑，再以本機快照讀取，避免 Samba 頁面快取造成清單過期
        from core.db_factory import (
            prepare_transfer_db_for_import,
            snapshot_sqlite_for_fresh_read,
        )

        req_folder, auto_warn = self._resolve_data_import_folder(runtime, folder)
        real_path, _share, t_err, warn = prepare_transfer_db_for_import(
            runtime.base_dir, for_write=False, folder=req_folder or None
        )
        if t_err:
            return None, t_err
        _, err = self._ensure_allowed_program(runtime, do_proc)
        if err:
            return None, err

        snap_path, cleanup = snapshot_sqlite_for_fresh_read(real_path)
        transfer_be = self._backend_for_path(runtime, snap_path)
        key = (kind or "").strip().upper()
        import time

        db_mtime = ""
        db_size = 0
        if real_path and os.path.isfile(real_path):
            try:
                st = os.stat(real_path)
                db_size = int(getattr(st, "st_size", 0) or 0)
                db_mtime = time.strftime(
                    "%Y/%m/%d %H:%M:%S", time.localtime(st.st_mtime)
                )
            except OSError:
                pass
        warn_out = "\n".join(x for x in (auto_warn, warn) if x)
        folder_out = req_folder or (os.path.dirname(real_path) if real_path else "")
        try:
            if key not in ("PURCHASE", "INVOICE"):
                return {
                    "kind": key,
                    "rows": [],
                    "columns": [],
                    "source_table": "",
                    "db_path": real_path,
                    "db_mtime": db_mtime,
                    "db_size": db_size,
                    "pending_count": 0,
                    "warning": warn_out,
                    "folder": folder_out,
                }, None
            grid, list_err = list_pending_import_grid(transfer_be, key)
            if list_err:
                return None, list_err
            rows = grid.get("rows") or []
            return {
                "kind": key,
                "rows": rows,
                "columns": grid.get("columns") or [],
                "source_table": grid.get("source_table") or "",
                "db_path": real_path,
                "db_mtime": db_mtime,
                "db_size": db_size,
                "pending_count": len(rows) if isinstance(rows, list) else 0,
                "warning": warn_out,
                "folder": folder_out,
            }, None
        finally:
            if cleanup:
                try:
                    os.remove(cleanup)
                except OSError:
                    pass

    def run_data_import(
        self,
        runtime: AppRuntime,
        do_proc: str,
        kind: str,
        selected_keys: Optional[List[str]] = None,
        folder: str = "",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not is_data_import_program(do_proc):
            return None, "此作業非資料匯入 (DATAIMPORT / DO_DATAIMPORT)。"
        req_folder, auto_folder_warn = self._resolve_data_import_folder(runtime, folder)
        transfer_be, company_be, err, _share_path, t_warn = self._backends_for_data_import(
            runtime,
            do_proc,
            for_write=True,
            folder=req_folder,
        )
        if err or transfer_be is None or company_be is None:
            return None, err or "無法連線資料庫。"
        progress_lines: List[str] = []

        def _progress(msg: str) -> None:
            if msg:
                progress_lines.append(str(msg))

        result = run_data_import(
            transfer_be,
            company_be,
            kind,
            selected_keys=selected_keys,
            progress=_progress,
        )
        payload = data_import_result_dict(result)
        # 將處理過程訊息附在結果，方便 Web／桌面顯示
        payload["progress_log"] = list(progress_lines)
        if progress_lines:
            # 避免與 result.message 末段重複：僅附加尚未含於 message 的過程列
            msg = str(payload.get("message") or "")
            extra = [ln for ln in progress_lines if ln and ln not in msg]
            if extra:
                payload["message"] = (msg + "\n\n--- 處理過程 ---\n" if msg else "") + "\n".join(
                    extra
                )
        if t_warn:
            msg = str(payload.get("message") or "")
            payload["message"] = (msg + "\n\n" if msg else "") + t_warn
        if auto_folder_warn:
            msg = str(payload.get("message") or "")
            payload["message"] = (msg + "\n\n" if msg else "") + auto_folder_warn
        # 業務失敗時仍回傳 payload（含 progress），err 供呼叫端判斷
        return payload, None if result.ok else (str(payload.get("message") or result.message))
