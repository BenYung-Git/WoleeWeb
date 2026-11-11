from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from services.app_service import AppRuntime, AppService

if TYPE_CHECKING:
    from ui.print_report_dialog import PrintReportDialog


def _qt_call(work):
    from services.qt_bridge import qt_call

    return qt_call(work)


def _print_report_dialog_cls():
    from ui.print_report_dialog import PrintReportDialog

    return PrintReportDialog


_dialog_cache: Dict[str, Any] = {}





def _phys_index(physical_fields: list, column_name: str) -> Optional[int]:

    key = (column_name or "").strip().upper()

    if not key:

        return None

    for i, f in enumerate(physical_fields):

        if f.strip().upper() == key:

            return i

    return None





def _cache_key(token: str, do_proc: str) -> str:

    return f"{token}:{do_proc.strip().upper()}"





def _report_proc_candidates(

    runtime: AppRuntime, do_proc: str, binding

) -> List[str]:

    """與 Windows WorkPage 一致，並補上 rule_proc / data_item 候選。"""

    candidates: List[str] = []

    seen: set[str] = set()



    def add(name: Optional[str]) -> None:

        s = (name or "").strip()

        if not s:

            return

        key = s.upper()

        if key in seen:

            return

        seen.add(key)

        candidates.append(s)



    prg = binding.menu_item

    data_prg = binding.data_item

    if prg and prg.proc_name:

        add(prg.proc_name)

    if data_prg and data_prg.proc_name:

        add(data_prg.proc_name)

    rule_proc = (binding.rule_proc or "").strip()

    if rule_proc:

        add(rule_proc)

        resolved = runtime.program_repo.find_by_do_proc(rule_proc)

        if resolved and resolved.proc_name:

            add(resolved.proc_name)

    add(do_proc)

    return candidates





class PrintReportService:

    """Web 列印服務：建立並快取 PrintReportDialog 執行個體。"""



    def __init__(self, app_service: AppService) -> None:

        self._app_service = app_service



    def clear_session(self, token: str) -> None:

        def _work() -> None:

            prefix = f"{token}:"

            for key in list(_dialog_cache.keys()):

                if key.startswith(prefix):

                    del _dialog_cache[key]



        _qt_call(_work)



    def _get_dialog(self, token: str, do_proc: str) -> Optional[PrintReportDialog]:

        return _dialog_cache.get(_cache_key(token, do_proc))



    def _build_dialog(

        self,

        runtime: AppRuntime,

        do_proc: str,

        selected_row: Optional[int],

    ) -> Tuple[Optional[PrintReportDialog], Optional[str]]:

        schema, err = self._app_service.resolve_work(runtime, do_proc, reload_program=False)

        if err or schema is None:

            return None, err or "無法解析作業。"



        do_proc_up = do_proc.strip().upper()

        table_up = schema.table_name.strip().upper()

        is_quot = (

            do_proc_up == "QUOTATION"

            or table_up == "QUOTATION"

            or "PRNQUOTATION" in do_proc_up

        )



        backend = self._app_service._backend_for_path(runtime, schema.db_path)

        if is_quot:

            try:

                rows = backend.fetch_rows(

                    schema.table_name,

                    "",

                    False,

                    limit=5000,

                    column_order=schema.physical_fields,

                )

                if not rows:

                    return None, "無資料可列印。"

            except Exception:

                return None, "無資料可列印。"



        binding = runtime.program_repo.resolve_program_binding(do_proc)

        report_proc_candidates = _report_proc_candidates(runtime, do_proc, binding)

        report_proc_name = report_proc_candidates[0] if report_proc_candidates else do_proc



        inv_col_idx: Optional[int] = None

        default_inv: Optional[str] = None

        physical_row: Optional[list] = None



        if selected_row is not None:

            data, derr = self._app_service.fetch_rows(runtime, do_proc, limit=5000)

            if derr or data is None:

                return None, derr or "查詢失敗。"

            physical_rows = data.get("physical_rows") or data.get("rows") or []

            if 0 <= selected_row < len(physical_rows):

                physical_row = list(physical_rows[selected_row])



        key_col = schema.print_doc_key_column

        if key_col:

            key_i = _phys_index(schema.physical_fields, key_col)

            if key_i is not None:

                inv_col_idx = key_i

                if physical_row is not None and key_i < len(physical_row):

                    t = (physical_row[key_i] or "").strip()

                    if t:

                        default_inv = t



        if schema.tx_files:

            tx_i: Optional[int] = None

            for i, name in enumerate(schema.physical_fields):

                if name.strip().upper() == "TX_KEY":

                    tx_i = i

                    break

            if inv_col_idx is None and tx_i is not None:

                inv_col_idx = tx_i

            if (

                default_inv is None

                and tx_i is not None

                and physical_row is not None

                and tx_i < len(physical_row)

            ):

                t = (physical_row[tx_i] or "").strip()

                if t:

                    default_inv = t



        dlg = _print_report_dialog_cls()(

            None,

            runtime.lang,

            schema.table_name,

            schema.physical_fields,

            schema.grid_fields,

            runtime.data_dict,

            backend,

            report_proc_name,

            runtime.mdb_path,

            runtime.base_dir,

            schema.menu_title,

            quotation_xls_mode=is_quot,

            quotation_current_row=list(physical_row)

            if (is_quot and physical_row is not None)

            else None,

            inv_column_index=inv_col_idx,

            default_inv_text=default_inv,

            user_data_mdb_path=runtime.user_data_path,

            company_co_key=runtime.session.company_key,

            auto_list_on_empty=False,

            report_proc_candidates=report_proc_candidates,

        )

        return dlg, None



    def init_dialog(

        self,

        token: str,

        runtime: AppRuntime,

        do_proc: str,

        selected_row: Optional[int],

    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:

        def _work() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:

            dlg, err = self._build_dialog(runtime, do_proc, selected_row)

            if err or dlg is None:

                return None, err

            _dialog_cache[_cache_key(token, do_proc)] = dlg

            return dlg.to_web_init_dict(), None



        return _qt_call(_work)



    def apply_defaults_on_report_change(

        self,

        token: str,

        do_proc: str,

        report_index: int,

    ) -> Tuple[Optional[Dict[str, str]], Optional[str]]:

        def _work() -> Tuple[Optional[Dict[str, str]], Optional[str]]:

            dlg = self._get_dialog(token, do_proc)

            if dlg is None:

                return None, "請先初始化列印對話框。"

            if 0 <= report_index < dlg._cmb_report.count():

                dlg._cmb_report.setCurrentIndex(report_index)

            dlg._apply_print_defaults_for_current_report(force=True)

            return {

                "inv_from": dlg._ed_inv_from.text(),

                "inv_to": dlg._ed_inv_to.text(),

                "date_from": dlg._ed_date_from.text(),

                "date_to": dlg._ed_date_to.text(),

                "is_list": dlg._selected_report_is_list(),

                "is_document": dlg._selected_report_is_document(),

                "is_finance": dlg._selected_report_is_finance(),

            }, None



        return _qt_call(_work)



    def _require_dialog(

        self, token: str, do_proc: str, params: dict

    ) -> Tuple[Optional[PrintReportDialog], Optional[str]]:

        dlg = self._get_dialog(token, do_proc)

        if dlg is None:

            return None, "請先初始化列印對話框。"

        dlg.apply_web_params(params)

        return dlg, None



    def preview(

        self,

        token: str,

        do_proc: str,

        params: dict,

    ) -> Tuple[Optional[dict], Optional[str]]:

        def _work() -> Tuple[Optional[dict], Optional[str]]:

            dlg, err = self._require_dialog(token, do_proc, params)

            if err or dlg is None:

                return None, err

            return dlg.web_preview(), None



        return _qt_call(_work)



    def print_report(

        self,

        token: str,

        do_proc: str,

        params: dict,

    ) -> Tuple[bool, str]:

        def _work() -> Tuple[bool, str]:

            dlg, err = self._require_dialog(token, do_proc, params)

            if err or dlg is None:

                return False, err or "請先初始化列印對話框。"

            return dlg.web_print()



        return _qt_call(_work)



    def export_pdf(

        self,

        token: str,

        do_proc: str,

        params: dict,

    ) -> Tuple[bool, str, bytes]:

        def _work() -> Tuple[bool, str, bytes]:

            dlg, err = self._require_dialog(token, do_proc, params)

            if err or dlg is None:

                return False, err or "請先初始化列印對話框。", b""

            return dlg.web_export_pdf()



        return _qt_call(_work)



    def export_xlsx(

        self,

        token: str,

        do_proc: str,

        params: dict,

    ) -> Tuple[bool, str, bytes]:

        def _work() -> Tuple[bool, str, bytes]:

            dlg, err = self._require_dialog(token, do_proc, params)

            if err or dlg is None:

                return False, err or "請先初始化列印對話框。", b""

            return dlg.web_export_xlsx()



        return _qt_call(_work)



    def export_docx(

        self,

        token: str,

        do_proc: str,

        params: dict,

    ) -> Tuple[bool, str, bytes]:

        def _work() -> Tuple[bool, str, bytes]:

            dlg, err = self._require_dialog(token, do_proc, params)

            if err or dlg is None:

                return False, err or "請先初始化列印對話框。", b""

            return dlg.web_export_docx()



        return _qt_call(_work)

    def email_text(
        self,
        token: str,
        do_proc: str,
        params: dict,
    ) -> Tuple[Optional[dict], Optional[str]]:
        def _work() -> Tuple[Optional[dict], Optional[str]]:
            dlg, err = self._require_dialog(token, do_proc, params)
            if err or dlg is None:
                return None, err
            return dlg.web_email_text(), None

        return _qt_call(_work)

    def pick_rows(
        self,
        token: str,
        do_proc: str,
        params: dict,
    ) -> Tuple[Optional[dict], Optional[str]]:
        def _work() -> Tuple[Optional[dict], Optional[str]]:
            dlg = self._get_dialog(token, do_proc)
            if dlg is None:
                return None, "請先初始化列印對話框。"
            dlg.apply_web_params_for_pick(params)
            data = dlg.web_pick_rows_dict()
            if not data.get("ok"):
                return None, data.get("message") or "無法取得選取資料。"
            return data, None

        return _qt_call(_work)

