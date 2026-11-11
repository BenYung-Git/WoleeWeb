from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import threading
from typing import Callable, Optional

import uvicorn
import base64

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from api.schemas import (
    ArapFilterRequest,
    ArapLoadResponse,
    ArapSaveRequest,
    AttachmentResolveResponse,
    CompanyListResponse,
    DataImportKindsResponse,
    DataImportFoldersResponse,
    DataImportPendingResponse,
    DataImportRunRequest,
    DataImportRunResponse,
    FetchRowsRequest,
    LastCompanyRequest,
    LastCompanyResponse,
    LoginRequest,
    LoginResponse,
    LookupRowsRequest,
    LookupRowsResponse,
    SessionResponse,
    MenuGroupResponse,
    MenuItemResponse,
    MenuResponse,
    OkResponse,
    PrintActionResponse,
    PrintEmailTextResponse,
    PrintDefaultsRequest,
    PrintDefaultsResponse,
    PrintInitRequest,
    PrintInitResponse,
    PrintParamsRequest,
    PrintPickRowsResponse,
    PrintPreviewResponse,
    PrintPrinterItem,
    PrintReportItem,
    QueryKindsResponse,
    PartyQueryFilterRequest,
    PartyQueryLoadRequest,
    PartyQueryLoadResponse,
    PrepareKeyRequest,
    PrepareKeyResponse,
    ReceiptPaymentLoadResponse,
    ReceiptPaymentSaveRequest,
    ReceiptPaymentSaveResponse,
    StockQueryFilterRequest,
    StockQueryLoadRequest,
    StockQueryLoadResponse,
    AccountQueryFilterRequest,
    AccountQueryLoadRequest,
    AccountQueryLoadResponse,
    RowMutationRequest,
    SetLanguageRequest,
    UiSettingsResponse,
    TxRowsRequest,
    TxRowsResponse,
    TxSaveRequest,
    WorkRowsResponse,
    WorkSchemaResponse,
    AiChatRequest,
    AiChatResponse,
    AiRelatedExportRequest,
    AiCommandOpenResponse,
    AiCommandSaveRequest,
    AiCommandSaveResponse,
    AiDocItem,
    AiDocListResponse,
    AiSettingsResponse,
    AiSettingsUpdateRequest,
    AiUploadRequest,
    RunQueryPrepareResponse,
    RunQueryConnectRequest,
    RunQueryConnectResponse,
    RunQueryExecuteRequest,
    RunQueryExecuteResponse,
    RunQuerySaveRequest,
    RunQuerySaveResponse,
    RunQueryExportRequest,
    RunQuerySavedRequest,
    RunQuerySavedResponse,
)
from api.session_store import session_store
from api.network import local_browser_url, print_web_startup_banner, web_access_urls
from services.app_service import AppService
from services.print_report_service import PrintReportService
from core.attachment_service import is_image_path, is_pdf_path
from core.menu_icon_resolver import resolve_menu_item_icon_key

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATIC_DIR = os.path.join(_ROOT, "web", "static")


def _get_base_dir() -> str:
    return _ROOT


def _get_app_service() -> AppService:
    return AppService(_get_base_dir())


def _extract_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-Session-Token", "").strip()


def _require_runtime(request: Request) -> "AppRuntime":
    from services.app_service import AppRuntime

    token = _extract_token(request)
    runtime = session_store.get(token)
    if runtime is None:
        raise HTTPException(status_code=401, detail="未登入或 session 已過期。")
    return runtime


def create_app(base_dir: Optional[str] = None) -> FastAPI:
    if base_dir:
        global _ROOT
        _ROOT = os.path.abspath(base_dir)

    app = FastAPI(title="企業管理系統 Web API", version="1.0.0")
    svc = AppService(_ROOT if base_dir is None else os.path.abspath(base_dir))
    print_svc = PrintReportService(svc)

    @app.get("/api/health")
    def health() -> dict:
        mode = (os.environ.get("WOLEE_WEB_MODE") or "web").strip().lower()
        return {"status": "ok", "mode": "web", "launcher_mode": mode}

    @app.get("/api/query-kinds", response_model=QueryKindsResponse)
    def list_query_kinds() -> QueryKindsResponse:
        from core.query_registry import kind_defs_for_api

        return QueryKindsResponse(kinds=kind_defs_for_api())

    @app.get("/api/settings/ui", response_model=UiSettingsResponse)
    def ui_settings(request: Request) -> UiSettingsResponse:
        mode = (os.environ.get("WOLEE_WEB_MODE") or "web").strip().lower()
        host = request.headers.get("host", "").split(":")[0] or "127.0.0.1"
        port = request.url.port or 8080
        web_url = f"http://{host}:{port}/"
        if mode == "both":
            hint = (
                "桌面程式與 Web 已同時執行。請用工作列或 Alt+Tab 切換至「企業管理系統」"
                "桌面視窗；或繼續使用本瀏覽器。"
            )
            return UiSettingsResponse(
                launcher_mode=mode,
                web_url=web_url,
                can_switch_desktop=True,
                switch_desktop_hint=hint,
            )
        hint = (
            "若要與 Windows 桌面介面隨時切換，請在本機執行：\n"
            "  python launcher.py --mode both\n"
            "啟動後可用桌面選單「介面 → 開啟 Web 介面」與本頁互換。"
        )
        return UiSettingsResponse(
            launcher_mode=mode,
            web_url=web_url,
            can_switch_desktop=False,
            switch_desktop_hint=hint,
        )

    @app.get("/api/companies", response_model=CompanyListResponse)
    def list_companies() -> CompanyListResponse:
        companies, err = svc.list_companies()
        if err:
            raise HTTPException(status_code=500, detail=err)
        return CompanyListResponse(companies=companies or ["GS"])

    @app.post("/api/auth/last-company", response_model=LastCompanyResponse)
    def last_company(body: LastCompanyRequest) -> LastCompanyResponse:
        last_co, err = svc.detect_last_company(body.user_no, body.password)
        if err:
            raise HTTPException(status_code=500, detail=err)
        return LastCompanyResponse(company_key=last_co)

    @app.post("/api/auth/login", response_model=LoginResponse)
    def login(body: LoginRequest) -> LoginResponse:
        runtime, err = svc.login(
            body.user_no,
            body.password,
            body.company_key,
            login_date=body.login_date,
        )
        if err or runtime is None:
            raise HTTPException(status_code=401, detail=err or "登入失敗。")
        token = session_store.create(runtime)
        return LoginResponse(
            token=token,
            user_no=runtime.session.user_no,
            company_key=runtime.session.company_key,
            group_no=runtime.session.group_no,
            group_level=runtime.session.group_level,
            login_date=runtime.session.login_date,
            company_currency=getattr(runtime.session, "company_currency", "") or "",
        )

    @app.get("/api/auth/me", response_model=SessionResponse)
    def auth_me(runtime=Depends(_require_runtime)) -> SessionResponse:
        return SessionResponse(
            user_no=runtime.session.user_no,
            company_key=runtime.session.company_key,
            group_no=runtime.session.group_no,
            group_level=runtime.session.group_level,
            login_date=runtime.session.login_date,
            company_currency=getattr(runtime.session, "company_currency", "") or "",
        )

    @app.post("/api/auth/logout", response_model=OkResponse)
    def logout(request: Request) -> OkResponse:
        token = _extract_token(request)
        if token:
            session_store.remove(token)
        return OkResponse(message="已登出。")

    @app.get("/api/menu", response_model=MenuResponse)
    def get_menu(runtime=Depends(_require_runtime)) -> MenuResponse:
        runtime.reload_metadata()
        groups = []
        for g in svc.menu_groups(runtime):
            items = [
                MenuItemResponse(
                    do_proc=it.do_proc,
                    title=it.get_title(runtime.lang),
                    work_file=it.work_file,
                    icon=resolve_menu_item_icon_key(
                        it.do_proc, it.get_title(runtime.lang)
                    ),
                    std_proc=bool(getattr(it, "std_proc", True)),
                    need_attach=bool(getattr(it, "need_attach", False)),
                    attach_path=(getattr(it, "attach_path", None) or "").strip(),
                    attach_key=(getattr(it, "attach_key", None) or "").strip(),
                    need_other=bool(getattr(it, "need_other", False)),
                    other_title=(getattr(it, "other_title", None) or "").strip(),
                )
                for it in g.items
            ]
            groups.append(
                MenuGroupResponse(
                    menu_type=g.menu_type,
                    title=g.get_title(runtime.lang),
                    items=items,
                )
            )
        hint = None
        if not groups:
            repo = runtime.program_repo
            total = len(getattr(repo, "_all_items", []) or [])
            visible = len(getattr(repo, "_items", []) or [])
            hint = (
                f"sys_data={runtime.mdb_path}；program 共 {total} 筆，"
                f"權限篩選後 {visible} 筆。"
            )
            if total == 0:
                hint += " Linux 請執行 scripts/migrate_mdb_to_sqlite.py 產生 sys_data.sqlite。"
        return MenuResponse(groups=groups, lang=runtime.lang, hint=hint)

    @app.post("/api/settings/language", response_model=OkResponse)
    def set_language(body: SetLanguageRequest, runtime=Depends(_require_runtime)) -> OkResponse:
        svc.set_language(runtime, body.lang)
        return OkResponse(message="語言已更新。")

    @app.get("/api/work/{do_proc}/schema", response_model=WorkSchemaResponse)
    def work_schema(do_proc: str, runtime=Depends(_require_runtime)) -> WorkSchemaResponse:
        schema, err = svc.resolve_work(runtime, do_proc, reload_program=True)
        if err or schema is None:
            raise HTTPException(status_code=400, detail=err or "無法開啟作業。")
        return WorkSchemaResponse(**svc.schema_to_dict(runtime, schema))

    @app.post("/api/work/{do_proc}/rows", response_model=WorkRowsResponse)
    def work_rows(
        do_proc: str,
        body: FetchRowsRequest,
        runtime=Depends(_require_runtime),
    ) -> WorkRowsResponse:
        data, err = svc.fetch_rows(
            runtime,
            do_proc,
            keyword=body.keyword,
            as_filter=body.as_filter,
            limit=body.limit,
            reload_program=body.reload_program,
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "查詢失敗。")
        return WorkRowsResponse(**data)

    @app.post("/api/work/{do_proc}/lookup/rows", response_model=LookupRowsResponse)
    def lookup_rows(
        do_proc: str,
        body: LookupRowsRequest,
        runtime=Depends(_require_runtime),
    ) -> LookupRowsResponse:
        data, err = svc.fetch_lookup_rows(
            runtime,
            do_proc,
            lookup_db=body.lookup_db,
            keyword=body.keyword,
            as_filter=body.as_filter,
            limit=body.limit,
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "Lookup 查詢失敗。")
        return LookupRowsResponse(**data)

    @app.post("/api/work/{do_proc}/prepare-key", response_model=PrepareKeyResponse)
    def prepare_save_key(
        do_proc: str,
        body: PrepareKeyRequest,
        runtime=Depends(_require_runtime),
    ) -> PrepareKeyResponse:
        data, err = svc.prepare_save_key(
            runtime, do_proc, body.values, body.mode, manual_key=body.manual_key
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "編號準備失敗。")
        return PrepareKeyResponse(**data)

    @app.post("/api/work/{do_proc}/insert", response_model=OkResponse)
    def insert_row(
        do_proc: str,
        body: RowMutationRequest,
        runtime=Depends(_require_runtime),
    ) -> OkResponse:
        ok, err = svc.insert_row(
            runtime,
            do_proc,
            body.values,
            manual_key=body.manual_key,
            skip_key_prepare=body.skip_key_prepare,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=err or "新增失敗。")
        return OkResponse(message="新增成功。")

    @app.put("/api/work/{do_proc}/update", response_model=OkResponse)
    def update_row(
        do_proc: str,
        body: RowMutationRequest,
        runtime=Depends(_require_runtime),
    ) -> OkResponse:
        ok, err = svc.update_row(runtime, do_proc, body.values, body.old_row)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "更新失敗。")
        return OkResponse(message="更新成功。")

    @app.delete("/api/work/{do_proc}/delete", response_model=OkResponse)
    def delete_row(
        do_proc: str,
        body: RowMutationRequest,
        runtime=Depends(_require_runtime),
    ) -> OkResponse:
        ok, err = svc.delete_row(runtime, do_proc, body.old_row)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "刪除失敗。")
        return OkResponse(message="刪除成功。")

    @app.post("/api/work/{do_proc}/tx/{tx_table}/rows", response_model=TxRowsResponse)
    def tx_rows(
        do_proc: str,
        tx_table: str,
        body: TxRowsRequest,
        runtime=Depends(_require_runtime),
    ) -> TxRowsResponse:
        data, err = svc.fetch_tx_rows(runtime, do_proc, tx_table, body.physical_row)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "查詢明細失敗。")
        return TxRowsResponse(**data)

    @app.post("/api/work/{do_proc}/form-values")
    def form_values(
        do_proc: str,
        body: RowMutationRequest,
        runtime=Depends(_require_runtime),
    ) -> dict:
        values, err = svc.get_form_values(runtime, do_proc, body.old_row)
        if err or values is None:
            raise HTTPException(status_code=400, detail=err or "無法讀取表單。")
        return {"values": values}

    @app.put("/api/work/{do_proc}/tx/{tx_table}/save", response_model=OkResponse)
    def save_tx_rows(
        do_proc: str,
        tx_table: str,
        body: TxSaveRequest,
        runtime=Depends(_require_runtime),
    ) -> OkResponse:
        ok, err = svc.save_tx_rows(
            runtime,
            do_proc,
            tx_table,
            body.physical_rows,
            body.master_form_values,
            body.master_row,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=err or "儲存明細失敗。")
        return OkResponse(message="明細已儲存。")

    @app.post("/api/work/{do_proc}/attachments", response_model=AttachmentResolveResponse)
    def resolve_attachments(
        do_proc: str,
        body: RowMutationRequest,
        runtime=Depends(_require_runtime),
    ) -> AttachmentResolveResponse:
        data, err = svc.resolve_attachments(runtime, do_proc, body.old_row)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法解析附件。")
        return AttachmentResolveResponse(**data)

    @app.get("/api/attachments/file")
    def attachment_file(
        path: str,
        request: Request,
        runtime=Depends(_require_runtime),
    ):
        """提供附件預覽（僅限 resolve_attachments 回傳之路徑）。"""
        token = _extract_token(request)
        if not token:
            raise HTTPException(status_code=401, detail="未登入。")
        fp = os.path.normpath(os.path.abspath(path or ""))
        if not os.path.isfile(fp):
            raise HTTPException(status_code=404, detail="找不到檔案。")
        if not (is_pdf_path(fp) or is_image_path(fp)):
            raise HTTPException(status_code=400, detail="不支援的附件類型。")
        media = "application/pdf" if is_pdf_path(fp) else "application/octet-stream"
        ext = os.path.splitext(fp)[1].lower()
        if ext in (".jpg", ".jpeg"):
            media = "image/jpeg"
        elif ext == ".png":
            media = "image/png"
        elif ext == ".gif":
            media = "image/gif"
        elif ext == ".webp":
            media = "image/webp"
        elif ext in (".tif", ".tiff"):
            media = "image/tiff"
        elif ext == ".bmp":
            media = "image/bmp"
        return FileResponse(fp, media_type=media, filename=os.path.basename(fp))

    @app.post("/api/work/{do_proc}/arap/load", response_model=ArapLoadResponse)
    def arap_load(
        do_proc: str,
        body: RowMutationRequest,
        runtime=Depends(_require_runtime),
    ) -> ArapLoadResponse:
        data, err = svc.load_arap_settlement(runtime, do_proc, body.old_row)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法載入清賬。")
        return ArapLoadResponse(**data)

    @app.post("/api/work/{do_proc}/receipt-payment/load", response_model=ReceiptPaymentLoadResponse)
    def receipt_payment_load(
        do_proc: str,
        body: RowMutationRequest,
        runtime=Depends(_require_runtime),
    ) -> ReceiptPaymentLoadResponse:
        data, err = svc.load_receipt_payment(runtime, do_proc, body.old_row)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法載入收付款。")
        return ReceiptPaymentLoadResponse(**data)

    @app.put("/api/work/{do_proc}/receipt-payment/save", response_model=ReceiptPaymentSaveResponse)
    def receipt_payment_save(
        do_proc: str,
        body: ReceiptPaymentSaveRequest,
        runtime=Depends(_require_runtime),
    ) -> ReceiptPaymentSaveResponse:
        ok, err, vou_key = svc.save_receipt_payment(runtime, do_proc, body.document)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "收付款儲存失敗。")
        msg = f"編號已儲存：VOU_KEY = {vou_key}" if vou_key else "收付款已儲存。"
        return ReceiptPaymentSaveResponse(ok=True, message=msg, vou_key=vou_key or "")

    @app.put("/api/work/{do_proc}/arap/save", response_model=OkResponse)
    def arap_save(
        do_proc: str,
        body: ArapSaveRequest,
        runtime=Depends(_require_runtime),
    ) -> OkResponse:
        ok, err = svc.save_arap_settlement(runtime, do_proc, body.document)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "清賬儲存失敗。")
        return OkResponse(message="清賬已儲存。")

    @app.post("/api/work/{do_proc}/arap/auto", response_model=ArapLoadResponse)
    def arap_auto(
        do_proc: str,
        body: ArapSaveRequest,
        runtime=Depends(_require_runtime),
    ) -> ArapLoadResponse:
        data = svc.auto_arap_settlement(body.document)
        return ArapLoadResponse(**data)

    @app.post("/api/work/{do_proc}/arap/filter", response_model=ArapLoadResponse)
    def arap_filter(
        do_proc: str,
        body: ArapFilterRequest,
        runtime=Depends(_require_runtime),
    ) -> ArapLoadResponse:
        data = svc.filter_arap_lines(
            body.document,
            body.keyword,
            as_filter=body.as_filter,
        )
        return ArapLoadResponse(**data)

    @app.post("/api/work/{do_proc}/party-query/load", response_model=PartyQueryLoadResponse)
    def party_query_load(
        do_proc: str,
        body: PartyQueryLoadRequest,
        runtime=Depends(_require_runtime),
    ) -> PartyQueryLoadResponse:
        data, err = svc.load_party_query(
            runtime,
            do_proc,
            body.old_row,
            party_index=body.party_index,
            date_from=body.date_from,
            date_to=body.date_to,
            tx_kinds=body.tx_kinds,
            tx_kind=body.tx_kind,
            party_key=body.party_key or "",
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "查詢失敗。")
        return PartyQueryLoadResponse(**data)

    @app.post("/api/work/{do_proc}/party-query/filter", response_model=PartyQueryLoadResponse)
    def party_query_filter(
        do_proc: str,
        body: PartyQueryFilterRequest,
        runtime=Depends(_require_runtime),
    ) -> PartyQueryLoadResponse:
        data = svc.filter_party_query_lines(
            body.lines,
            body.keyword,
            as_filter=body.as_filter,
        )
        payload = {
            "mode": body.mode or "AR",
            "lines": data.get("lines") or [],
            "totals": data.get("totals") or {},
            "selected_index": data.get("selected_index"),
            "lang": runtime.lang,
        }
        return PartyQueryLoadResponse(**payload)

    @app.post("/api/work/{do_proc}/stock-query/load", response_model=StockQueryLoadResponse)
    def stock_query_load(
        do_proc: str,
        body: StockQueryLoadRequest,
        runtime=Depends(_require_runtime),
    ) -> StockQueryLoadResponse:
        data, err = svc.load_stock_query(
            runtime,
            do_proc,
            body.old_row,
            stock_index=body.stock_index,
            date_from=body.date_from,
            date_to=body.date_to,
            tx_kinds=body.tx_kinds,
            stock_key=body.stock_key or "",
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "查詢失敗。")
        return StockQueryLoadResponse(**data)

    @app.post("/api/work/{do_proc}/stock-query/filter", response_model=StockQueryLoadResponse)
    def stock_query_filter(
        do_proc: str,
        body: StockQueryFilterRequest,
        runtime=Depends(_require_runtime),
    ) -> StockQueryLoadResponse:
        data = svc.filter_stock_query_lines(
            body.lines,
            body.keyword,
            as_filter=body.as_filter,
        )
        payload = {
            "lines": data.get("lines") or [],
            "totals": data.get("totals") or {},
            "selected_index": data.get("selected_index"),
            "lang": runtime.lang,
        }
        return StockQueryLoadResponse(**payload)

    @app.post("/api/work/{do_proc}/account-query/load", response_model=AccountQueryLoadResponse)
    def account_query_load(
        do_proc: str,
        body: AccountQueryLoadRequest,
        runtime=Depends(_require_runtime),
    ) -> AccountQueryLoadResponse:
        data, err = svc.load_account_query(
            runtime,
            do_proc,
            body.old_row,
            account_index=body.account_index,
            account_key=body.account_key,
            date_from=body.date_from,
            date_to=body.date_to,
            tx_kinds=body.tx_kinds,
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "查詢失敗。")
        return AccountQueryLoadResponse(**data)

    @app.post("/api/work/{do_proc}/account-query/filter", response_model=AccountQueryLoadResponse)
    def account_query_filter(
        do_proc: str,
        body: AccountQueryFilterRequest,
        runtime=Depends(_require_runtime),
    ) -> AccountQueryLoadResponse:
        data = svc.filter_account_query_lines(
            body.lines,
            body.keyword,
            as_filter=body.as_filter,
        )
        payload = {
            "lines": data.get("lines") or [],
            "totals": data.get("totals") or {},
            "selected_index": data.get("selected_index"),
            "lang": runtime.lang,
        }
        return AccountQueryLoadResponse(**payload)

    @app.get("/api/work/{do_proc}/import/kinds", response_model=DataImportKindsResponse)
    def data_import_kinds(
        do_proc: str,
        runtime=Depends(_require_runtime),
    ) -> DataImportKindsResponse:
        data, err = svc.data_import_kinds(runtime, do_proc)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法載入匯入選項。")
        return DataImportKindsResponse(**data)

    @app.get("/api/work/{do_proc}/import/folders", response_model=DataImportFoldersResponse)
    def data_import_folders(
        do_proc: str,
        path: str = "",
        runtime=Depends(_require_runtime),
    ) -> DataImportFoldersResponse:
        data, err = svc.data_import_folders(runtime, do_proc, path=path)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法列出來源資料夾。")
        return DataImportFoldersResponse(**data)

    @app.get("/api/work/{do_proc}/import/pending", response_model=DataImportPendingResponse)
    def data_import_pending(
        do_proc: str,
        kind: str,
        response: Response,
        folder: str = "",
        runtime=Depends(_require_runtime),
    ) -> DataImportPendingResponse:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        data, err = svc.data_import_pending(runtime, do_proc, kind, folder=folder)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法載入待匯入資料。")
        return DataImportPendingResponse(**data)

    @app.post("/api/work/{do_proc}/import/run", response_model=DataImportRunResponse)
    def data_import_run(
        do_proc: str,
        body: DataImportRunRequest,
        runtime=Depends(_require_runtime),
    ) -> DataImportRunResponse:
        data, err = svc.run_data_import(
            runtime,
            do_proc,
            body.kind,
            body.selected_keys,
            folder=body.folder or "",
        )
        # 連線／參數錯誤：無 payload
        if data is None:
            raise HTTPException(status_code=400, detail=err or "匯入失敗。")
        # 業務失敗仍回傳完整處理訊息（ok=false），供 Web 顯示進度
        if err and not data.get("message"):
            data["message"] = err
            data["ok"] = False
        return DataImportRunResponse(**data)

    def _print_init_response(data: dict) -> PrintInitResponse:
        return PrintInitResponse(
            no_report=data.get("no_report", False),
            message=data.get("message"),
            doc_no_label=data.get("doc_no_label", ""),
            reports=[PrintReportItem(**r) for r in data.get("reports", [])],
            printers=[PrintPrinterItem(**p) for p in data.get("printers", [])],
            report_index=data.get("report_index", 0),
            printer_index=data.get("printer_index", 0),
            inv_from=data.get("inv_from", ""),
            inv_to=data.get("inv_to", ""),
            date_from=data.get("date_from", ""),
            date_to=data.get("date_to", ""),
            lang=data.get("lang", "CHN"),
            is_list=data.get("is_list", False),
            is_document=data.get("is_document", False),
        )

    def _print_api_error(exc: BaseException) -> HTTPException:
        if isinstance(exc, TimeoutError):
            return HTTPException(status_code=504, detail=str(exc) or "列印操作逾時。")
        if isinstance(exc, RuntimeError):
            return HTTPException(status_code=503, detail=str(exc) or "列印服務不可用。")
        return HTTPException(status_code=500, detail=str(exc) or "列印失敗。")

    @app.post("/api/work/{do_proc}/print/init", response_model=PrintInitResponse)
    def print_init(
        do_proc: str,
        body: PrintInitRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ) -> PrintInitResponse:
        token = _extract_token(request)
        try:
            data, err = print_svc.init_dialog(token, runtime, do_proc, body.selected_row)
        except (RuntimeError, TimeoutError) as exc:
            raise _print_api_error(exc) from exc
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法初始化列印。")
        return _print_init_response(data)

    @app.post("/api/work/{do_proc}/print/defaults", response_model=PrintDefaultsResponse)
    def print_defaults(
        do_proc: str,
        body: PrintDefaultsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ) -> PrintDefaultsResponse:
        token = _extract_token(request)
        try:
            data, err = print_svc.apply_defaults_on_report_change(
                token, do_proc, body.report_index
            )
        except (RuntimeError, TimeoutError) as exc:
            raise _print_api_error(exc) from exc
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法更新預設值。")
        return PrintDefaultsResponse(**data)

    @app.post("/api/work/{do_proc}/print/pick-rows", response_model=PrintPickRowsResponse)
    def print_pick_rows(
        do_proc: str,
        body: PrintParamsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ) -> PrintPickRowsResponse:
        token = _extract_token(request)
        try:
            data, err = print_svc.pick_rows(token, do_proc, body.model_dump())
        except (RuntimeError, TimeoutError) as exc:
            raise _print_api_error(exc) from exc
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法取得選取資料。")
        return PrintPickRowsResponse(**data)

    @app.post("/api/work/{do_proc}/print/preview", response_model=PrintPreviewResponse)
    def print_preview(
        do_proc: str,
        body: PrintParamsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ) -> PrintPreviewResponse:
        token = _extract_token(request)
        try:
            data, err = print_svc.preview(token, do_proc, body.model_dump())
        except (RuntimeError, TimeoutError) as exc:
            raise _print_api_error(exc) from exc
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "預覽失敗。")
        return PrintPreviewResponse(**data)

    @app.post("/api/work/{do_proc}/print/email-text", response_model=PrintEmailTextResponse)
    def print_email_text(
        do_proc: str,
        body: PrintParamsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ) -> PrintEmailTextResponse:
        token = _extract_token(request)
        try:
            data, err = print_svc.email_text(token, do_proc, body.model_dump())
        except (RuntimeError, TimeoutError) as exc:
            raise _print_api_error(exc) from exc
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法取得郵件內容。")
        return PrintEmailTextResponse(**data)

    @app.post("/api/work/{do_proc}/print/print", response_model=PrintActionResponse)
    def print_execute(
        do_proc: str,
        body: PrintParamsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ) -> PrintActionResponse:
        token = _extract_token(request)
        ok, msg = print_svc.print_report(token, do_proc, body.model_dump())
        if not ok:
            raise HTTPException(status_code=400, detail=msg or "列印失敗。")
        return PrintActionResponse(ok=True, message=msg)

    @app.post("/api/work/{do_proc}/print/export/pdf")
    def print_export_pdf(
        do_proc: str,
        body: PrintParamsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ):
        token = _extract_token(request)
        ok, msg, data = print_svc.export_pdf(token, do_proc, body.model_dump())
        if not ok:
            raise HTTPException(status_code=400, detail=msg or "匯出 PDF 失敗。")
        title = (runtime.lang == "CHN" and "report") or "report"
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{title}.pdf"'},
        )

    @app.post("/api/work/{do_proc}/print/export/xlsx")
    def print_export_xlsx(
        do_proc: str,
        body: PrintParamsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ):
        token = _extract_token(request)
        ok, msg, data = print_svc.export_xlsx(token, do_proc, body.model_dump())
        if not ok:
            raise HTTPException(status_code=400, detail=msg or "匯出 XLSX 失敗。")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="report.xlsx"'},
        )

    @app.post("/api/work/{do_proc}/print/export/docx")
    def print_export_docx(
        do_proc: str,
        body: PrintParamsRequest,
        request: Request,
        runtime=Depends(_require_runtime),
    ):
        token = _extract_token(request)
        ok, msg, data = print_svc.export_docx(token, do_proc, body.model_dump())
        if not ok:
            raise HTTPException(status_code=400, detail=msg or "匯出 DOCX 失敗。")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="report.docx"'},
        )

    def _ai_catalog(runtime) -> list:
        from core.ai_assistant_service import catalog_from_programs

        if not getattr(runtime, "_program_loaded", False):
            runtime.reload_metadata()
        items = getattr(runtime.program_repo, "_items", None) or []
        return catalog_from_programs(items, runtime.lang)

    def _ai_work_context(runtime, do_proc: str, table_name: str = ""):
        proc = (do_proc or "").strip()
        table = (table_name or "").strip()
        if not proc:
            return None, table, None
        schema, err = svc.resolve_work(runtime, proc)
        if err or schema is None:
            return None, table, err
        backend = svc._backend_for_path(runtime, schema.db_path)
        return backend, (table or schema.table_name or ""), None

    def _ai_related_search(
        runtime,
        keyword: str,
        fields=None,
        include_date: bool = True,
        include_qty: bool = True,
    ) -> dict:
        return svc.search_related_records(
            runtime,
            keyword,
            fields=fields,
            include_date=include_date,
            include_qty=include_qty,
        )

    @app.post("/api/ai/related/export/xlsx")
    def ai_related_export_xlsx(
        body: AiRelatedExportRequest, runtime=Depends(_require_runtime)
    ):
        ok, filename, data = svc.export_related_records_xlsx(
            runtime,
            body.keyword,
            fields=body.fields or None,
            include_date=bool(body.include_date),
            include_qty=bool(body.include_qty),
        )
        if not ok:
            raise HTTPException(status_code=400, detail=filename or "匯出 XLSX 失敗。")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/ai/chat", response_model=AiChatResponse)
    def ai_chat(body: AiChatRequest, runtime=Depends(_require_runtime)) -> AiChatResponse:
        from core.ai_assistant_service import chat as ai_chat_fn

        backend, table_name, _err = _ai_work_context(
            runtime, body.active_do_proc, body.table_name
        )
        hist = [{"role": h.role, "content": h.content} for h in (body.history or [])]
        data = ai_chat_fn(
            base_dir=runtime.base_dir,
            user_no=runtime.session.user_no,
            message=body.message,
            catalog=_ai_catalog(runtime),
            history=hist,
            active_do_proc=body.active_do_proc or "",
            lang=runtime.lang,
            backend=backend,
            table_name=table_name,
            related_search_fn=lambda keyword, fields=None, include_date=True, include_qty=True: _ai_related_search(
                runtime,
                keyword,
                fields=fields,
                include_date=include_date,
                include_qty=include_qty,
            ),
        )
        return AiChatResponse(**data)

    @app.get("/api/ai/docs", response_model=AiDocListResponse)
    def ai_docs(runtime=Depends(_require_runtime)) -> AiDocListResponse:
        from core.ai_assistant_service import list_user_docs

        try:
            docs = list_user_docs(runtime.base_dir, runtime.session.user_no)
            items: list = []
            for d in docs:
                try:
                    items.append(AiDocItem(**d))
                except Exception:
                    continue
            return AiDocListResponse(docs=items)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"無法讀取文件清單：{e}") from e

    @app.post("/api/ai/upload", response_model=AiDocItem)
    def ai_upload(body: AiUploadRequest, runtime=Depends(_require_runtime)) -> AiDocItem:
        from core.ai_assistant_service import save_user_document

        raw = (body.content_base64 or "").strip()
        if "," in raw and raw.lower().startswith("data:"):
            raw = raw.split(",", 1)[1]
        if not raw:
            raise HTTPException(status_code=400, detail="未收到檔案內容。")
        try:
            data = base64.b64decode(raw, validate=False)
        except Exception:
            raise HTTPException(status_code=400, detail="檔案內容無法解碼。")
        try:
            rec, err = save_user_document(
                runtime.base_dir,
                str(runtime.session.user_no or ""),
                body.name or "upload.bin",
                data,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"上傳失敗：{e}") from e
        if err or rec is None:
            raise HTTPException(status_code=400, detail=err or "上傳失敗。")
        try:
            return AiDocItem(**rec)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"上傳回應格式錯誤：{e}") from e

    @app.delete("/api/ai/docs/{doc_id}", response_model=OkResponse)
    def ai_delete_doc(doc_id: str, runtime=Depends(_require_runtime)) -> OkResponse:
        from core.ai_assistant_service import delete_user_document

        ok, err = delete_user_document(runtime.base_dir, runtime.session.user_no, doc_id)
        if not ok:
            raise HTTPException(status_code=404, detail=err or "找不到該文件。")
        return OkResponse(message="已刪除。")

    @app.post("/api/ai/command/open", response_model=AiCommandOpenResponse)
    def ai_command_open(runtime=Depends(_require_runtime)) -> AiCommandOpenResponse:
        data, err = svc.prepare_ai_command_work(runtime)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法開啟 AI_COMMAND。")
        return AiCommandOpenResponse(**data)

    @app.post("/api/ai/command/save", response_model=AiCommandSaveResponse)
    def ai_command_save(
        body: AiCommandSaveRequest, runtime=Depends(_require_runtime)
    ) -> AiCommandSaveResponse:
        msgs = [{"role": m.role, "content": m.content} for m in (body.messages or [])]
        rec, err = svc.save_ai_command_chat(
            runtime,
            msgs,
            title=body.title or "",
            prompt=body.prompt or "",
            reply=body.reply or "",
        )
        if err or rec is None:
            raise HTTPException(status_code=400, detail=err or "儲存失敗。")
        chn = str(runtime.lang or "").upper().startswith("C")
        return AiCommandSaveResponse(
            ok=True,
            message=("已儲存指令。" if chn else "Command saved."),
            cmd_code=str(rec.get("cmd_code") or ""),
            cmd_title=str(rec.get("cmd_title") or ""),
            do_proc=str(rec.get("do_proc") or "AI_COMMAND"),
        )

    @app.post("/api/run-query/prepare", response_model=RunQueryPrepareResponse)
    def run_query_prepare(runtime=Depends(_require_runtime)) -> RunQueryPrepareResponse:
        data, err = svc.prepare_run_query(runtime)
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法準備執行查詢。")
        return RunQueryPrepareResponse(**data)

    @app.post("/api/run-query/connect", response_model=RunQueryConnectResponse)
    def run_query_connect(
        body: RunQueryConnectRequest, runtime=Depends(_require_runtime)
    ) -> RunQueryConnectResponse:
        ok, msg = svc.run_query_test_connection(
            runtime, body.conn.model_dump() if body.conn else {}
        )
        return RunQueryConnectResponse(ok=ok, message=msg)

    @app.post("/api/run-query/execute", response_model=RunQueryExecuteResponse)
    def run_query_execute(
        body: RunQueryExecuteRequest, runtime=Depends(_require_runtime)
    ) -> RunQueryExecuteResponse:
        data, err = svc.run_query_execute(
            runtime,
            body.sql or "",
            body.conn.model_dump() if body.conn else {},
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "執行失敗。")
        return RunQueryExecuteResponse(**data)

    @app.post("/api/run-query/save", response_model=RunQuerySaveResponse)
    def run_query_save(
        body: RunQuerySaveRequest, runtime=Depends(_require_runtime)
    ) -> RunQuerySaveResponse:
        rec, err = svc.run_query_save(
            runtime,
            body.sql or "",
            description=body.description or "",
            code=body.code or "",
        )
        if err or rec is None:
            raise HTTPException(status_code=400, detail=err or "儲存失敗。")
        chn = str(runtime.lang or "").upper().startswith("C")
        return RunQuerySaveResponse(
            ok=True,
            message=("已儲存至 RUN_QUERY。" if chn else "Saved to RUN_QUERY."),
            qry_code=str(rec.get("qry_code") or ""),
            qry_desc=str(rec.get("qry_desc") or ""),
            do_proc=str(rec.get("do_proc") or "RUNQUERY"),
        )

    @app.post("/api/run-query/saved", response_model=RunQuerySavedResponse)
    def run_query_saved(
        body: RunQuerySavedRequest, runtime=Depends(_require_runtime)
    ) -> RunQuerySavedResponse:
        data, err = svc.run_query_saved_rows(
            runtime, keyword=body.keyword or "", as_filter=bool(body.as_filter)
        )
        if err or data is None:
            raise HTTPException(status_code=400, detail=err or "無法讀取 RUN_QUERY。")
        return RunQuerySavedResponse(**data)

    @app.post("/api/run-query/export/xlsx")
    def run_query_export_xlsx(
        body: RunQueryExportRequest, runtime=Depends(_require_runtime)
    ):
        ok, name, data = svc.run_query_export_xlsx(
            runtime,
            body.columns or [],
            body.rows or [],
            filename_stem=body.filename_stem or "run_query",
        )
        if not ok:
            raise HTTPException(status_code=400, detail=name or "匯出失敗。")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/ai/settings", response_model=AiSettingsResponse)
    def ai_get_settings(runtime=Depends(_require_runtime)) -> AiSettingsResponse:
        from core.ai_settings import settings_for_client

        return AiSettingsResponse(
            **settings_for_client(
                runtime.base_dir, runtime.session.user_no, lang=runtime.lang
            )
        )

    @app.put("/api/ai/settings", response_model=AiSettingsResponse)
    def ai_save_settings(
        body: AiSettingsUpdateRequest, runtime=Depends(_require_runtime)
    ) -> AiSettingsResponse:
        from core.ai_settings import save_ai_settings, settings_for_client

        save_ai_settings(
            runtime.base_dir,
            runtime.session.user_no,
            api_key=body.api_key,
            model=body.model or None,
            base_url=body.base_url or None,
            clear_api_key=bool(body.clear_api_key),
        )
        return AiSettingsResponse(
            **settings_for_client(
                runtime.base_dir, runtime.session.user_no, lang=runtime.lang
            )
        )

    @app.get("/")
    def index():
        index_path = os.path.join(_STATIC_DIR, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Web 前端未安裝。")

    if os.path.isdir(_STATIC_DIR):
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


class _SuppressUvicornShutdownNoise(logging.Filter):
    """關閉時 uvicorn/starlette lifespan 的 CancelledError 為正常現象，不印 ERROR。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.ERROR:
            return True
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is asyncio.CancelledError:
                return False
        msg = record.getMessage()
        return "CancelledError" not in msg and "lifespan" not in msg.lower()


class _WoleeUvicornServer(uvicorn.Server):
    """收到 SIGINT/SIGTERM 時除停止 uvicorn 外，可呼叫額外關閉回呼（例如結束 Qt 事件迴圈）。"""

    shutdown_hook: Optional[Callable[[], None]] = None

    def handle_exit(self, sig, frame) -> None:  # noqa: ARG002
        super().handle_exit(sig, frame)
        hook = self.shutdown_hook
        if hook is None:
            return
        try:
            hook()
        except Exception:
            pass


def _uvicorn_config(app, host: str, port: int) -> uvicorn.Config:
    """建立 uvicorn 設定；關閉 lifespan 可避免 Ctrl+C 時 lifespan CancelledError 噪音。"""
    cfg = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="off",
    )
    for name in ("uvicorn.error", "uvicorn"):
        logging.getLogger(name).addFilter(_SuppressUvicornShutdownNoise())
    return cfg


class WebServerManager:
    """背景 Web 伺服器管理（桌面/Web 雙模式切換用）。"""

    _instance: Optional["WebServerManager"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[_WoleeUvicornServer] = None
        self._host = "0.0.0.0"
        self._port = 8080
        self._base_dir = _ROOT
        self._running = False
        self._shutdown_lock = threading.Lock()
        self._shutdown_hook: Optional[Callable[[], None]] = None

    @classmethod
    def instance(cls) -> "WebServerManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = WebServerManager()
            return cls._instance

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        return local_browser_url(self._host, self._port)

    @property
    def access_urls(self) -> list[str]:
        return web_access_urls(self._host, self._port)

    def configure(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        base_dir: Optional[str] = None,
        shutdown_hook: Optional[Callable[[], None]] = None,
    ) -> None:
        self._host = host
        self._port = port
        if base_dir:
            self._base_dir = os.path.abspath(base_dir)
        if shutdown_hook is not None:
            self._shutdown_hook = shutdown_hook

    def start(self, blocking: bool = False) -> bool:
        if self.is_running:
            return True

        app = create_app(self._base_dir)
        hook = self._shutdown_hook

        def _run() -> None:
            self._running = True
            server: Optional[_WoleeUvicornServer] = None
            try:
                print_web_startup_banner(self._host, self._port)
                config = _uvicorn_config(app, self._host, self._port)
                server = _WoleeUvicornServer(config)
                server.shutdown_hook = hook
                with self._shutdown_lock:
                    self._server = server
                server.run()
            finally:
                self._running = False
                with self._shutdown_lock:
                    if server is not None and self._server is server:
                        self._server = None

        if blocking:
            _run()
            return True

        self._thread = threading.Thread(
            target=_run, daemon=True, name="WoleeWebServer"
        )
        self._thread.start()
        return True

    def request_shutdown(self) -> None:
        """從主控台 Ctrl+C 等觸發：先優雅結束 uvicorn（不立即 force_exit）。"""
        with self._shutdown_lock:
            server = self._server
            if server is not None:
                server.should_exit = True

    def stop(self, timeout: float = 8.0) -> None:
        with self._shutdown_lock:
            self._running = False
            server = self._server
            if server is not None:
                server.should_exit = True
            thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
            if thread.is_alive() and server is not None:
                with self._shutdown_lock:
                    server.force_exit = True
                thread.join(timeout=min(timeout, 3.0))
        with self._shutdown_lock:
            if self._thread is thread and not (thread and thread.is_alive()):
                self._thread = None


def install_main_thread_interrupt(
    mgr: WebServerManager,
    extra: Optional[Callable[[], None]] = None,
) -> None:
    """
    主執行緒額外註冊 Ctrl+C：停止 uvicorn 並執行 extra（例如 app.quit）。
    uvicorn 在背景執行緒時，僅靠其 signal handler 可能無法結束 Qt 事件迴圈。
    """

    def _handle(signum, frame) -> None:  # noqa: ARG001
        sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        print(f"\n收到 {sig_name}，正在停止伺服器…", flush=True)
        mgr.stop()
        if extra is not None:
            try:
                extra()
            except Exception:
                pass
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle)


def run_server(host: str = "0.0.0.0", port: int = 8080, base_dir: Optional[str] = None) -> None:
    """前景執行 Web 伺服器（web 模式）。"""
    mgr = WebServerManager.instance()
    mgr.configure(host=host, port=port, base_dir=base_dir)
    try:
        mgr.start(blocking=True)
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
    finally:
        mgr.stop()
