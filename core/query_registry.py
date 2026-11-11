"""查詢類型登錄表：新增查詢類型時主要在此註冊 match 規則與 API 欄位名。

流程（AI／Web／桌面）：
1. resolve_query_kind → 判斷作業屬於哪種查詢
2. match_query_program → 從選單 catalog 配對查詢作業
3. load 時帶 index_param / key_param（見 QueryKindDef）

新增查詢類型步驟：
- 實作 core/*_query_service.py（is_*、load_*、find_*_index）
- 在此檔 QUERY_KIND_DEFS 加一筆 + _register_matchers 掛載 match 函式
- app.js QUERY_KIND_REGISTRY 加一筆（openModal / reload）
- api/schemas + server 若沿用既有 *-query/load 模式
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

MatchFn = Callable[[str, str, str], bool]


@dataclass(frozen=True)
class QueryKindDef:
    kind: str
    table_name: str
    api_suffix: str
    key_param: str
    index_param: str
    default_tx_kinds: Tuple[str, ...]
    utterance_pattern: str
    work_file: str
    blob_hint_pattern: str
    min_catalog_score: int = 60


QUERY_KIND_DEFS: Tuple[QueryKindDef, ...] = (
    QueryKindDef(
        kind="account",
        table_name="ACCOUNT",
        api_suffix="account-query",
        key_param="account_key",
        index_param="account_index",
        default_tx_kinds=("ACC",),
        utterance_pattern=r"account|acc|賬戶|帳戶",
        work_file="ACCOUNT",
        blob_hint_pattern=r"賬戶|帳戶|ACCOUNT",
        min_catalog_score=60,
    ),
    QueryKindDef(
        kind="stock",
        table_name="STOCK",
        api_suffix="stock-query",
        key_param="stock_key",
        index_param="stock_index",
        default_tx_kinds=("PUR", "INV", "ADJ", "TRI"),
        utterance_pattern=r"stock|inventory|stk|存貨|庫存",
        work_file="STOCK",
        blob_hint_pattern=r"存貨|庫存|STOCK|INVENTORY",
        min_catalog_score=60,
    ),
    QueryKindDef(
        kind="party",
        table_name="CUSTVEND",
        api_suffix="party-query",
        key_param="party_key",
        index_param="party_index",
        default_tx_kinds=("INV", "REC", "PUR", "PAY"),
        utterance_pattern=r"顧客|客戶|供應商|廠商|cust|vend",
        work_file="CUSTVEND",
        blob_hint_pattern=r"顧客|客戶|供應商|廠商",
        min_catalog_score=70,
    ),
)

QUERY_KIND_ORDER: Tuple[str, ...] = tuple(d.kind for d in QUERY_KIND_DEFS)

_MATCHERS: Dict[str, MatchFn] = {}


def _norm_label(text: str) -> str:
    return re.sub(r"[\s\-_/\.]+", "", (text or "").lower())


def _register_matchers() -> None:
    if _MATCHERS:
        return
    from core.account_query_service import is_account_query_program
    from core.party_query_service import resolve_party_query_mode
    from core.stock_query_service import is_stock_query_program

    _MATCHERS["account"] = lambda proc, tbl, other: is_account_query_program(
        proc, tbl, other
    )
    _MATCHERS["stock"] = lambda proc, tbl, other: is_stock_query_program(
        proc, tbl, other
    )
    _MATCHERS["party"] = lambda proc, tbl, other: resolve_party_query_mode(
        proc, tbl, other
    ) is not None


def kind_def(kind: str) -> Optional[QueryKindDef]:
    for d in QUERY_KIND_DEFS:
        if d.kind == kind:
            return d
    return None


def kind_defs_for_api() -> List[Dict[str, Any]]:
    """供 /api/query-kinds 與前端同步 metadata（不含 match 函式）。"""
    return [
        {
            "kind": d.kind,
            "table_name": d.table_name,
            "api_suffix": d.api_suffix,
            "key_param": d.key_param,
            "index_param": d.index_param,
            "default_tx_kinds": list(d.default_tx_kinds),
            "tab_type": f"{d.kind}-query",
        }
        for d in QUERY_KIND_DEFS
    ]


def resolve_query_kind(
    do_proc: str,
    table_name: str = "",
    other_title: str = "",
) -> Optional[str]:
    """依作業識別查詢類型；順序見 QUERY_KIND_ORDER。"""
    _register_matchers()
    for k in QUERY_KIND_ORDER:
        fn = _MATCHERS.get(k)
        if fn and fn(do_proc or "", table_name or "", other_title or ""):
            return k
    return None


def resolve_query_kind_from_catalog_item(item: Dict[str, str]) -> Optional[str]:
    proc = str(item.get("do_proc") or "")
    other = str(item.get("other_title") or "")
    work = str(item.get("work_file") or "")
    kind = resolve_query_kind(proc, work, other)
    if kind:
        return kind
    wu = work.strip().upper()
    for d in QUERY_KIND_DEFS:
        if wu == d.table_name:
            return d.kind
    return None


def extract_entity_key_from_action(act: Dict[str, Any]) -> str:
    """從 AI action 取查詢鍵值（相容 keyword / entity_key / 各 *_key）。"""
    for field in ("entity_key", "keyword"):
        v = str(act.get(field) or "").strip()
        if v:
            return v
    for d in QUERY_KIND_DEFS:
        v = str(act.get(d.key_param) or "").strip()
        if v:
            return v
    return ""


def build_query_action(
    do_proc: str,
    keyword: str,
    *,
    catalog_item: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """組出標準 query action（含 entity_key 與對應 key_param）。"""
    kw = (keyword or "").strip()
    act: Dict[str, Any] = {
        "type": "query",
        "do_proc": do_proc,
        "keyword": kw,
        "entity_key": kw,
    }
    kind = None
    if catalog_item:
        kind = resolve_query_kind_from_catalog_item(catalog_item)
    if not kind:
        kind = resolve_query_kind(do_proc)
    if kind:
        defn = kind_def(kind)
        if defn and kw:
            act[defn.key_param] = kw
    return act


def _match_catalog_for_kind(
    catalog: Sequence[Dict[str, str]],
    text: str,
    defn: QueryKindDef,
) -> Optional[Dict[str, str]]:
    q = (text or "").strip()
    qu = q.upper()
    qn = _norm_label(q)
    wants = bool(re.search(defn.utterance_pattern, q, re.I))
    best: Optional[Tuple[int, Dict[str, str]]] = None
    for it in catalog:
        title = it.get("title") or ""
        other = it.get("other_title") or ""
        work = (it.get("work_file") or "").upper()
        blob = f"{title} {other}"
        score = 0
        if work == defn.work_file and re.search(r"查詢|QUERY", blob, re.I):
            score += 90
        elif work == defn.work_file and wants:
            score += 80
        if re.search(defn.blob_hint_pattern, blob, re.I) and re.search(
            r"查詢|QUERY", blob, re.I
        ):
            score += 95
        if wants and re.search(defn.blob_hint_pattern, blob, re.I):
            score += 70
        for label in (title, other):
            ln = _norm_label(label)
            min_label = 4 if defn.kind == "party" else 3
            if len(ln) >= min_label and ln in qn:
                score += 85
            elif defn.kind == "party" and ln and any(
                ln in _norm_label(tok) or _norm_label(tok) in ln
                for tok in re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
            ):
                score += 40
        if defn.work_file in qu and work == defn.work_file:
            score += 60
        if score > 0 and (best is None or score > best[0]):
            best = (score, it)
    if best and best[0] >= defn.min_catalog_score:
        return best[1]
    return None


def match_query_program(
    catalog: Sequence[Dict[str, str]],
    text: str,
    keyword: str = "",
    *,
    match_program_fn: Optional[Callable[..., Optional[Dict[str, str]]]] = None,
) -> Optional[Dict[str, str]]:
    """從選單 catalog 配對查詢作業（AI 意圖解析用）。"""
    q = (text or "").lower()
    if re.search(r"查詢|query", q, re.I):
        for defn in QUERY_KIND_DEFS:
            if re.search(defn.utterance_pattern, q, re.I):
                hit = _match_catalog_for_kind(catalog, text, defn)
                if hit:
                    return hit
        best: Optional[Tuple[int, Dict[str, str]]] = None
        for it in catalog:
            blob = f"{it.get('title') or ''} {it.get('other_title') or ''}"
            if not re.search(r"查詢|QUERY", blob, re.I):
                continue
            score = 50
            work = (it.get("work_file") or "").upper()
            if work and work.lower() in q.replace(" ", ""):
                score += 40
            if best is None or score > best[0]:
                best = (score, it)
        if best:
            return best[1]
    if match_program_fn is not None:
        hit = match_program_fn(
            catalog, text, exclude_tokens=[keyword] if keyword else None
        )
        if hit:
            return hit
    for defn in QUERY_KIND_DEFS:
        if re.search(defn.utterance_pattern, q, re.I):
            hit = _match_catalog_for_kind(catalog, text, defn)
            if hit:
                return hit
    return None
