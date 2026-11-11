from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    user_no: str
    password: str
    company_key: str = ""
    login_date: str = ""


class LoginResponse(BaseModel):
    token: str = ""
    user_no: str
    company_key: str
    group_no: str = ""
    group_level: Optional[int] = None
    login_date: str = ""
    company_currency: str = ""


class SessionResponse(BaseModel):
    user_no: str
    company_key: str
    group_no: str = ""
    group_level: Optional[int] = None
    login_date: str = ""
    company_currency: str = ""


class CompanyListResponse(BaseModel):
    companies: List[str]


class LastCompanyRequest(BaseModel):
    user_no: str
    password: str


class LastCompanyResponse(BaseModel):
    company_key: Optional[str] = None


class MenuItemResponse(BaseModel):
    do_proc: str
    title: str
    work_file: Optional[str] = None
    icon: str = "applications-system"
    std_proc: bool = True
    need_attach: bool = False
    attach_path: str = ""
    attach_key: str = ""
    need_other: bool = False
    other_title: str = ""


class MenuGroupResponse(BaseModel):
    menu_type: str
    title: str
    items: List[MenuItemResponse]


class MenuResponse(BaseModel):
    groups: List[MenuGroupResponse]
    lang: str
    hint: Optional[str] = None


class AttachmentFileItem(BaseModel):
    path: str
    name: str
    kind: str = "other"


class AttachmentResolveResponse(BaseModel):
    lookup_column: str = ""
    key_value: str = ""
    folder: str = ""
    files: List[AttachmentFileItem] = Field(default_factory=list)
    show_attach_folder: bool = False
    not_found_message: str = ""


class ArapSettlementHeader(BaseModel):
    vou_key: str = ""
    settle_date: str = ""
    party_key: str = ""
    party_name: str = ""
    settle_amount: str = ""
    exchange_diff: str = ""


class ArapSettlementLine(BaseModel):
    tx_key: str = ""
    inv_no: str = ""
    date: str = ""
    currency: str = ""
    rate: str = ""
    net_amt: str = ""
    paid_amt: str = ""
    balance: str = ""
    pay_amount: str = ""
    discount: str = ""
    in_trx: bool = False
    old_pay_amount: str = ""
    old_discount: str = ""


class ArapSettlementDocument(BaseModel):
    mode: str = "AR"
    header: ArapSettlementHeader = Field(default_factory=ArapSettlementHeader)
    lines: List[ArapSettlementLine] = Field(default_factory=list)


class ArapLoadResponse(BaseModel):
    mode: str = "AR"
    header: ArapSettlementHeader
    lines: List[ArapSettlementLine] = Field(default_factory=list)
    totals: Dict[str, str] = Field(default_factory=dict)
    lang: str = "CHN"
    selected_index: Optional[int] = None


class ArapFilterRequest(BaseModel):
    document: Dict[str, Any] = Field(default_factory=dict)
    keyword: str = ""
    as_filter: bool = False


class ArapSaveRequest(BaseModel):
    document: Dict[str, Any] = Field(default_factory=dict)


class ReceiptPaymentHeader(BaseModel):
    mode: str = "AR"
    inv_key: str = ""
    inv_no: str = ""
    inv_date: str = ""
    party_key: str = ""
    party_name: str = ""
    currency: str = ""
    rate: str = "1"
    net_amt: str = "0"
    paid_amt: str = "0"
    balance: str = "0"


class ReceiptPaymentForm(BaseModel):
    pay_amount: str = "0"
    pay_date: str = ""
    pay_method: str = ""
    bank: str = ""
    cheque: str = ""
    chq_date: str = ""
    remark: str = ""
    debit_ac: str = ""
    credit_ac: str = ""


class ReceiptPaymentLoadResponse(BaseModel):
    mode: str = "AR"
    vou_key: str = ""
    header: ReceiptPaymentHeader
    form: ReceiptPaymentForm
    lang: str = "CHN"
    other_title: str = ""


class ReceiptPaymentSaveRequest(BaseModel):
    document: Dict[str, Any] = Field(default_factory=dict)


class ReceiptPaymentSaveResponse(BaseModel):
    ok: bool = True
    message: str = ""
    vou_key: str = ""


class PartyQueryInfo(BaseModel):
    key: str = ""
    name: str = ""
    contact: str = ""
    tel: str = ""
    mobile: str = ""
    credit_limit: str = ""
    remain_credit: str = ""


class PartyQueryLineItem(BaseModel):
    date: str = ""
    tx_category: str = ""
    tx_key: str = ""
    currency: str = ""
    rate: str = ""
    inv_amt: str = ""
    paid_amt: str = ""
    recv_amt: str = ""
    settle_amt: str = ""


class PartyQueryLoadRequest(BaseModel):
    old_row: List[str] = Field(default_factory=list)
    # <0：依 old_row 定位；>=0：明確索引（FIRST=0）
    party_index: int = -1
    party_key: str = ""
    date_from: str = ""
    date_to: str = ""
    # 多選：INV/REC/PUR/PAY；空清單＝不選；未傳時可用 tx_kind 相容舊客戶端
    tx_kinds: Optional[List[str]] = None
    tx_kind: str = "ALL"


class PartyQueryFilterRequest(BaseModel):
    mode: str = "AR"
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    keyword: str = ""
    as_filter: bool = False


class PartyQueryLoadResponse(BaseModel):
    mode: str = "AR"
    parties: List[PartyQueryInfo] = Field(default_factory=list)
    party_index: int = 0
    party: PartyQueryInfo = Field(default_factory=PartyQueryInfo)
    lines: List[PartyQueryLineItem] = Field(default_factory=list)
    totals: Dict[str, str] = Field(default_factory=dict)
    date_from: str = ""
    date_to: str = ""
    tx_kinds: List[str] = Field(default_factory=lambda: ["INV", "REC", "PUR", "PAY"])
    tx_kind: str = "ALL"
    lang: str = "CHN"
    selected_index: Optional[int] = None


class StockQueryInfo(BaseModel):
    key: str = ""
    category: str = ""
    brand: str = ""
    model: str = ""
    desc: str = ""


class StockQueryLineItem(BaseModel):
    date: str = ""
    tx_category: str = ""
    tx_key: str = ""
    qty: str = ""
    unit: str = ""
    weight: str = ""
    wgt_unit: str = ""
    warehouse: str = ""
    unit_price: str = ""
    amount: str = ""
    unit_cost: str = ""
    cost_amt: str = ""


class StockQueryLoadRequest(BaseModel):
    old_row: List[str] = Field(default_factory=list)
    # <0：依 old_row 定位；>=0：明確索引（FIRST=0）
    stock_index: int = -1
    stock_key: str = ""
    date_from: str = ""
    date_to: str = ""
    tx_kinds: Optional[List[str]] = None


class StockQueryFilterRequest(BaseModel):
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    keyword: str = ""
    as_filter: bool = False


class StockQueryLoadResponse(BaseModel):
    stocks: List[StockQueryInfo] = Field(default_factory=list)
    stock_index: int = 0
    stock: StockQueryInfo = Field(default_factory=StockQueryInfo)
    lines: List[StockQueryLineItem] = Field(default_factory=list)
    totals: Dict[str, str] = Field(default_factory=dict)
    date_from: str = ""
    date_to: str = ""
    tx_kinds: List[str] = Field(default_factory=lambda: ["PUR", "INV", "ADJ", "TRI"])
    lang: str = "CHN"
    selected_index: Optional[int] = None


class AccountQueryInfo(BaseModel):
    key: str = ""
    parent_key: str = ""
    acc_type: str = ""
    acc_level: str = ""
    name: str = ""


class AccountQueryLineItem(BaseModel):
    date: str = ""
    vou_key: str = ""
    currency: str = ""
    rate: str = ""
    dr_amt: str = ""
    cr_amt: str = ""
    remark: str = ""


class AccountQueryLoadRequest(BaseModel):
    old_row: List[str] = Field(default_factory=list)
    # <0：依 old_row 定位；>=0：明確索引（FIRST=0）
    account_index: int = -1
    account_key: str = ""
    date_from: str = ""
    date_to: str = ""
    tx_kinds: Optional[List[str]] = None


class AccountQueryFilterRequest(BaseModel):
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    keyword: str = ""
    as_filter: bool = False


class AccountQueryLoadResponse(BaseModel):
    accounts: List[AccountQueryInfo] = Field(default_factory=list)
    account_index: int = 0
    account: AccountQueryInfo = Field(default_factory=AccountQueryInfo)
    lines: List[AccountQueryLineItem] = Field(default_factory=list)
    totals: Dict[str, str] = Field(default_factory=dict)
    date_from: str = ""
    date_to: str = ""
    tx_kinds: List[str] = Field(default_factory=lambda: ["ACC"])
    lang: str = "CHN"
    selected_index: Optional[int] = None


class QueryKindMetaItem(BaseModel):
    kind: str = ""
    table_name: str = ""
    api_suffix: str = ""
    key_param: str = ""
    index_param: str = ""
    default_tx_kinds: List[str] = Field(default_factory=list)
    tab_type: str = ""


class QueryKindsResponse(BaseModel):
    kinds: List[QueryKindMetaItem] = Field(default_factory=list)


class DataImportKindItem(BaseModel):
    kind: str
    label: str = ""
    detail: str = ""


class DataImportKindsResponse(BaseModel):
    kinds: List[DataImportKindItem] = Field(default_factory=list)
    default_folder: str = ""
    default_transfer_path: str = ""
    default_note: str = ""


class DataImportFoldersResponse(BaseModel):
    path: str = ""
    parent: str = ""
    folders: List[str] = Field(default_factory=list)
    has_transfer: bool = False
    transfer_path: str = ""


class DataImportPendingRow(BaseModel):
    key: str
    tx_type: str = ""
    label: str = ""
    cells: List[str] = Field(default_factory=list)


class DataImportPendingColumn(BaseModel):
    name: str
    title: str = ""


class DataImportPendingResponse(BaseModel):
    kind: str
    rows: List[DataImportPendingRow] = Field(default_factory=list)
    columns: List[DataImportPendingColumn] = Field(default_factory=list)
    source_table: str = ""
    db_path: str = ""
    db_mtime: str = ""
    db_size: int = 0
    pending_count: int = 0
    warning: str = ""
    folder: str = ""


class DataImportRunRequest(BaseModel):
    kind: str
    selected_keys: List[str] = Field(default_factory=list)
    folder: str = ""


class DataImportTableResult(BaseModel):
    source_table: str
    dest_table: str
    rows_imported: int = 0
    error: str = ""


class DataImportRunResponse(BaseModel):
    ok: bool
    kind: str = ""
    message: str = ""
    total_rows: int = 0
    tables: List[DataImportTableResult] = Field(default_factory=list)
    progress_log: List[str] = Field(default_factory=list)


class SetLanguageRequest(BaseModel):
    lang: Literal["CHN", "ENG"]


class UiSettingsResponse(BaseModel):
    launcher_mode: str = "web"
    web_url: str = ""
    can_switch_desktop: bool = False
    switch_desktop_hint: str = ""


class WorkSchemaResponse(BaseModel):
    do_proc: str
    table_name: str
    menu_title: str
    fields: List[str]
    physical_fields: List[str] = Field(default_factory=list)
    form_fields: List[str] = Field(default_factory=list)
    columns: List[Dict[str, Any]]
    form_columns: List[Dict[str, Any]] = Field(default_factory=list)
    tx_files: List[str] = Field(default_factory=list)
    print_doc_key_column: Optional[str] = None
    work_actions: Dict[str, Any] = Field(default_factory=dict)
    key_code_column: Optional[str] = None
    num_type_column: Optional[str] = None
    num_control_column: Optional[str] = None
    num_digit: int = 8
    proc_name: str = ""
    lang: str = "CHN"


class WorkRowsResponse(BaseModel):
    do_proc: str
    table_name: str
    menu_title: str = ""
    fields: List[str]
    physical_fields: List[str] = Field(default_factory=list)
    form_fields: List[str] = Field(default_factory=list)
    form_columns: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[Dict[str, Any]]
    rows: List[List[str]]
    physical_rows: List[List[str]] = Field(default_factory=list)
    total: int
    tx_files: List[str] = Field(default_factory=list)
    print_doc_key_column: Optional[str] = None
    work_actions: Dict[str, Any] = Field(default_factory=dict)
    search_indices: Optional[List[int]] = None
    search_ret_field: Optional[str] = None
    search_ret_value: Optional[str] = None
    key_code_column: Optional[str] = None
    num_type_column: Optional[str] = None
    num_control_column: Optional[str] = None
    num_digit: int = 8
    proc_name: str = ""


class LookupRowsRequest(BaseModel):
    lookup_db: str
    keyword: str = ""
    as_filter: bool = False
    limit: int = 5000


class LookupRowsResponse(BaseModel):
    lookup_db: str
    fields: List[str] = Field(default_factory=list)
    physical_fields: List[str] = Field(default_factory=list)
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    physical_rows: List[List[str]] = Field(default_factory=list)
    total: int = 0


class TxRowsRequest(BaseModel):
    physical_row: List[str] = Field(default_factory=list)


class TxSaveRequest(BaseModel):
    physical_rows: List[List[str]] = Field(default_factory=list)
    master_form_values: Dict[str, str] = Field(default_factory=dict)
    master_row: List[str] = Field(default_factory=list)


class TxRowsResponse(BaseModel):
    tx_table: str
    fields: List[str]
    physical_fields: List[str] = Field(default_factory=list)
    columns: List[Dict[str, Any]]
    rows: List[List[str]]
    physical_rows: List[List[str]] = Field(default_factory=list)
    read_only: bool = False
    filter_column: Optional[str] = None
    filter_value: Optional[str] = None


class FetchRowsRequest(BaseModel):
    keyword: str = ""
    as_filter: bool = False
    limit: int = 100000
    reload_program: bool = False


class RowMutationRequest(BaseModel):
    values: Dict[str, str] = Field(default_factory=dict)
    old_row: List[str] = Field(default_factory=list)
    manual_key: str = ""
    skip_key_prepare: bool = False


class PrepareKeyRequest(BaseModel):
    values: Dict[str, str] = Field(default_factory=dict)
    mode: str = "add"
    manual_key: str = ""


class PrepareKeyResponse(BaseModel):
    values: Dict[str, str] = Field(default_factory=dict)
    manual_required: bool = False
    key_field: str = ""
    key_label: str = ""
    suggested_key: str = ""
    lookup_db: str = ""
    lookup_ret: str = ""
    table_name: str = ""


class OkResponse(BaseModel):
    ok: bool = True
    message: str = ""


class ErrorResponse(BaseModel):
    detail: str


class PrintInitRequest(BaseModel):
    selected_row: Optional[int] = None


class PrintReportItem(BaseModel):
    index: int
    title: str
    rpt_type: str = ""


class PrintPrinterItem(BaseModel):
    index: int
    name: str


class PrintInitResponse(BaseModel):
    no_report: bool
    message: Optional[str] = None
    doc_no_label: str
    reports: List[PrintReportItem]
    printers: List[PrintPrinterItem]
    report_index: int = 0
    printer_index: int = 0
    inv_from: str = ""
    inv_to: str = ""
    date_from: str = ""
    date_to: str = ""
    lang: str = "CHN"
    is_list: bool = False
    is_document: bool = False


class PrintParamsRequest(BaseModel):
    report_index: int = 0
    printer_index: int = 0
    inv_from: str = ""
    inv_to: str = ""
    date_from: str = ""
    date_to: str = ""


class PrintDefaultsRequest(BaseModel):
    report_index: int = 0


class PrintDefaultsResponse(BaseModel):
    inv_from: str = ""
    inv_to: str = ""
    date_from: str = ""
    date_to: str = ""
    is_list: bool = False
    is_document: bool = False


class PrintPickColumnItem(BaseModel):
    name: str
    title: str = ""


class PrintPickRowsResponse(BaseModel):
    ok: bool = True
    fields: List[str] = []
    columns: List[PrintPickColumnItem] = []
    rows: List[List[str]] = []
    key_values: List[str] = []


class PrintPreviewResponse(BaseModel):
    ok: bool
    message: str = ""
    kind: Literal["html", "pdf"] = "html"
    html: Optional[str] = None
    pdfs_base64: Optional[List[str]] = None


class PrintActionResponse(BaseModel):
    ok: bool
    message: str = ""


class PrintEmailTextResponse(BaseModel):
    subject: str = ""
    plain_text: str = ""
    hint: str = ""


class AiChatHistoryItem(BaseModel):
    role: str = "user"
    content: str = ""


class AiChatRequest(BaseModel):
    message: str
    history: List[AiChatHistoryItem] = Field(default_factory=list)
    active_do_proc: str = ""
    table_name: str = ""


class AiChatResponse(BaseModel):
    reply: str = ""
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, str]] = Field(default_factory=list)
    llm_enabled: bool = False


class AiRelatedExportRequest(BaseModel):
    keyword: str = ""
    fields: List[str] = Field(default_factory=list)
    include_date: bool = True
    include_qty: bool = True


class AiDocItem(BaseModel):
    id: str = ""
    name: str = ""
    size: int = 0
    uploaded_at: str = ""
    chunks: Optional[int] = None


class AiDocListResponse(BaseModel):
    docs: List[AiDocItem] = Field(default_factory=list)


class AiUploadRequest(BaseModel):
    name: str
    content_base64: str


class AiModelOption(BaseModel):
    id: str
    label: str = ""


class AiSettingsResponse(BaseModel):
    model: str = "gpt-4o-mini"
    active_model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    has_api_key: bool = False
    api_key_hint: str = ""
    user_api_key_set: bool = False
    llm_enabled: bool = False
    config_source: str = "none"
    default_model: str = "gpt-4o-mini"
    default_base_url: str = "https://api.openai.com/v1"
    models: List[AiModelOption] = Field(default_factory=list)
    allow_custom_model: bool = True


class AiSettingsUpdateRequest(BaseModel):
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    clear_api_key: bool = False


class AiCommandOpenResponse(BaseModel):
    do_proc: str = "AI_COMMAND"
    title: str = ""
    table_name: str = "AI_COMMAND"


class AiCommandSaveRequest(BaseModel):
    messages: List[AiChatHistoryItem] = Field(default_factory=list)
    title: str = ""
    prompt: str = ""
    reply: str = ""


class AiCommandSaveResponse(BaseModel):
    ok: bool = True
    message: str = ""
    cmd_code: str = ""
    cmd_title: str = ""
    do_proc: str = "AI_COMMAND"


class RunQueryDbKindItem(BaseModel):
    kind: str
    label: str = ""


class RunQueryPrepareResponse(BaseModel):
    do_proc: str = "RUNQUERY"
    title: str = ""
    table_name: str = "RUN_QUERY"
    visible_rows: int = 12
    db_kinds: List[RunQueryDbKindItem] = Field(default_factory=list)
    default_kind: str = "SQLITE"
    default_path: str = ""


class RunQueryConnSpec(BaseModel):
    kind: str = "SQLITE"
    path: str = ""
    host: str = "localhost"
    port: int = 0
    database: str = ""
    user: str = ""
    password: str = ""
    driver: str = ""


class RunQueryConnectRequest(BaseModel):
    conn: RunQueryConnSpec = Field(default_factory=RunQueryConnSpec)


class RunQueryConnectResponse(BaseModel):
    ok: bool = False
    message: str = ""


class RunQueryExecuteRequest(BaseModel):
    sql: str = ""
    conn: RunQueryConnSpec = Field(default_factory=RunQueryConnSpec)


class RunQueryExecuteResponse(BaseModel):
    columns: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    sql: str = ""
    total: int = 0
    rowcount: int = -1
    is_result_set: bool = True
    message: str = ""


class RunQuerySaveRequest(BaseModel):
    sql: str = ""
    description: str = ""
    code: str = ""


class RunQuerySaveResponse(BaseModel):
    ok: bool = True
    message: str = ""
    qry_code: str = ""
    qry_desc: str = ""
    do_proc: str = "RUNQUERY"


class RunQueryExportRequest(BaseModel):
    columns: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    filename_stem: str = "run_query"


class RunQuerySavedRequest(BaseModel):
    keyword: str = ""
    as_filter: bool = False


class RunQuerySavedResponse(BaseModel):
    lookup_db: str = "RUN_QUERY"
    fields: List[str] = Field(default_factory=list)
    physical_fields: List[str] = Field(default_factory=list)
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    physical_rows: List[List[str]] = Field(default_factory=list)
    total: int = 0
