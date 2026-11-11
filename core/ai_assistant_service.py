"""AI 助理：日常問答、私人文件檢索、企業系統操作意圖。"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.db_backend import DbBackendBase


ALLOWED_DOC_EXT = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".pdf",
    ".docx",
    ".xlsx",
    ".xls",
}


def _dir_is_writable(path: str) -> bool:
    """探測目錄是否可建立／寫入／刪除（Samba 唯讀掛載常會在此失敗）。"""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, f".wolee_write_probe_{os.getpid()}")
        with open(probe, "wb") as f:
            f.write(b"1")
        os.remove(probe)
        return True
    except OSError:
        return False


def _local_ai_docs_root() -> str:
    """本機可寫的 AI 文件根目錄（避開 Samba 唯讀）。"""
    env = (os.environ.get("WOLEE_AI_DOCS_DIR") or "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    if os.name == "nt":
        base = (os.environ.get("LOCALAPPDATA") or "").strip() or os.path.expanduser("~")
        return os.path.join(base, "WoleeWeb", "ai_private_docs")
    xdg = (os.environ.get("XDG_DATA_HOME") or "").strip()
    if xdg:
        return os.path.join(os.path.abspath(xdg), "WoleeWeb", "ai_private_docs")
    return os.path.join(
        os.path.expanduser("~"), ".local", "share", "WoleeWeb", "ai_private_docs"
    )


def resolve_ai_docs_root(base_dir: str = "") -> str:
    """
    解析 AI 私人文件／設定存放根目錄。
    優先：WOLEE_AI_DOCS_DIR → base_dir/ai_private_docs（可寫時）→ 本機 fallback。
    """
    env = (os.environ.get("WOLEE_AI_DOCS_DIR") or "").strip()
    if env:
        root = os.path.abspath(os.path.expanduser(env))
        os.makedirs(root, exist_ok=True)
        return root
    preferred = os.path.join(os.path.abspath(base_dir or "."), "ai_private_docs")
    if _dir_is_writable(preferred):
        return preferred
    fallback = _local_ai_docs_root()
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _safe_user_dir(base_dir: str, user_no: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", str(user_no or "user").strip()) or "user"
    root = resolve_ai_docs_root(base_dir)
    path = os.path.join(root, raw)
    if _dir_is_writable(path):
        return path
    # 根目錄可寫但使用者子目錄不可寫（或 Samba ACL）→ 強制本機
    local_root = _local_ai_docs_root()
    path = os.path.join(local_root, raw)
    os.makedirs(path, exist_ok=True)
    if not _dir_is_writable(path):
        raise OSError(
            f"無法寫入 AI 文件目錄：{path}。"
            f"請設定環境變數 WOLEE_AI_DOCS_DIR 指向可寫目錄，"
            f"或開放 Samba／本機寫入權限。"
        )
    return path


def _index_path(user_dir: str) -> str:
    return os.path.join(user_dir, "index.json")


def _coerce_doc_meta(d: Any) -> Optional[Dict[str, Any]]:
    """將 index 單筆文件資料正規化；損壞資料略過。"""
    if not isinstance(d, dict):
        return None
    doc_id = str(d.get("id") or "").strip()
    if not doc_id:
        return None
    name = str(d.get("name") or doc_id).strip() or doc_id
    try:
        size = int(d.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size < 0:
        size = 0
    uploaded_at = str(d.get("uploaded_at") or "").strip()
    return {
        "id": doc_id,
        "name": name,
        "size": size,
        "uploaded_at": uploaded_at,
    }


def _load_index(user_dir: str) -> Dict[str, Any]:
    p = _index_path(user_dir)
    if not os.path.isfile(p):
        return {"docs": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("docs"), list):
            # 保留完整 rec（含 chunks），僅確保 docs 為 list
            return data
    except Exception:
        pass
    return {"docs": []}


def _save_index(user_dir: str, data: Dict[str, Any]) -> None:
    with open(_index_path(user_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _tokenize(text: str) -> List[str]:
    s = (text or "").lower()
    parts = re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{1,}", s)
    out: List[str] = []
    for p in parts:
        if re.fullmatch(r"[\u4e00-\u9fff]+", p) and len(p) > 2:
            for i in range(len(p) - 1):
                out.append(p[i : i + 2])
            out.append(p)
        else:
            out.append(p)
    return out


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in {".txt", ".md", ".csv", ".json"}:
        for enc in ("utf-8-sig", "utf-8", "cp950", "big5", "latin-1"):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode("utf-8", errors="replace")
    if ext == ".pdf":
        try:
            import fitz  # pymupdf

            doc = fitz.open(stream=data, filetype="pdf")
            parts = [page.get_text("text") or "" for page in doc]
            doc.close()
            return "\n".join(parts)
        except Exception as e:
            return f"（無法讀取 PDF：{e}）"
    if ext == ".docx":
        try:
            import io
            from docx import Document

            d = Document(io.BytesIO(data))
            return "\n".join(p.text for p in d.paragraphs if p.text)
        except Exception as e:
            return f"（無法讀取 DOCX：{e}）"
    if ext in {".xlsx", ".xls"}:
        try:
            import io
            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            lines: List[str] = []
            for ws in wb.worksheets:
                lines.append(f"# {ws.title}")
                for row in ws.iter_rows(max_row=200, max_col=20, values_only=True):
                    cells = [str(c) for c in row if c is not None and str(c).strip()]
                    if cells:
                        lines.append("\t".join(cells))
            return "\n".join(lines)
        except Exception as e:
            return f"（無法讀取試算表：{e}）"
    return ""


def _chunk_text(text: str, size: int = 700) -> List[str]:
    t = re.sub(r"\r\n?", "\n", text or "").strip()
    if not t:
        return []
    chunks: List[str] = []
    buf = ""
    for para in t.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = para[:size]
            rest = para[size:]
            while len(rest) > size:
                chunks.append(rest[:size])
                rest = rest[size:]
            if rest:
                buf = rest
    if buf:
        chunks.append(buf)
    return chunks[:400]


def list_user_docs(base_dir: str, user_no: str) -> List[Dict[str, Any]]:
    user_dir = _safe_user_dir(base_dir, user_no)
    idx = _load_index(user_dir)
    out: List[Dict[str, Any]] = []
    for d in idx.get("docs") or []:
        meta = _coerce_doc_meta(d)
        if meta:
            out.append(meta)
    return out


def save_user_document(
    base_dir: str, user_no: str, filename: str, data: bytes
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in ALLOWED_DOC_EXT:
            return None, "僅支援 TXT、MD、CSV、JSON、PDF、DOCX、XLSX、XLS。"
        if not data:
            return None, "檔案是空的。"
        if len(data) > 12 * 1024 * 1024:
            return None, "檔案超過 12MB。"
        text = extract_text_from_bytes(filename, data)
        chunks = _chunk_text(text)
        if not chunks:
            return None, "無法從檔案抽出文字內容。"
        try:
            user_dir = _safe_user_dir(base_dir, user_no)
        except OSError as e:
            return None, str(e)
        doc_id = uuid.uuid4().hex[:12]
        store_name = f"{doc_id}{ext}"
        fpath = os.path.join(user_dir, store_name)
        with open(fpath, "wb") as f:
            f.write(data)
        rec = {
            "id": doc_id,
            "name": os.path.basename(str(filename or store_name)),
            "file": store_name,
            "size": int(len(data)),
            "uploaded_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
            "chunks": chunks,
        }
        idx = _load_index(user_dir)
        docs = list(idx.get("docs") or [])
        docs.append(rec)
        idx["docs"] = docs
        _save_index(user_dir, idx)
        return {
            "id": doc_id,
            "name": rec["name"],
            "size": rec["size"],
            "uploaded_at": rec["uploaded_at"],
            "chunks": len(chunks),
        }, None
    except OSError as e:
        return (
            None,
            f"無法寫入檔案：{e}。"
            f"若在 Samba／網路磁碟上執行，請設定 WOLEE_AI_DOCS_DIR 為本機可寫目錄"
            f"（例如 ~/.local/share/WoleeWeb/ai_private_docs）。",
        )
    except Exception as e:
        return None, f"上傳失敗：{e}"


def delete_user_document(base_dir: str, user_no: str, doc_id: str) -> Tuple[bool, Optional[str]]:
    user_dir = _safe_user_dir(base_dir, user_no)
    idx = _load_index(user_dir)
    docs = idx.get("docs") or []
    found = None
    keep = []
    for d in docs:
        if str(d.get("id")) == str(doc_id):
            found = d
        else:
            keep.append(d)
    if found is None:
        return False, "找不到該文件。"
    fpath = os.path.join(user_dir, str(found.get("file") or ""))
    if os.path.isfile(fpath):
        try:
            os.remove(fpath)
        except Exception:
            pass
    idx["docs"] = keep
    _save_index(user_dir, idx)
    return True, None


def search_user_documents(
    base_dir: str, user_no: str, query: str, limit: int = 5
) -> List[Dict[str, str]]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    user_dir = _safe_user_dir(base_dir, user_no)
    idx = _load_index(user_dir)
    scored: List[Tuple[float, Dict[str, str]]] = []
    for d in idx.get("docs") or []:
        name = str(d.get("name") or "")
        for ch in d.get("chunks") or []:
            blob = f"{name}\n{ch}"
            toks = set(_tokenize(blob))
            hit = sum(1 for t in q_tokens if t in toks)
            if name and any(t in name.lower() for t in q_tokens):
                hit += 2
            if hit <= 0:
                continue
            snippet = ch.strip().replace("\n", " ")
            if len(snippet) > 420:
                snippet = snippet[:420] + "…"
            scored.append(
                (
                    float(hit),
                    {"id": str(d.get("id") or ""), "name": name, "snippet": snippet},
                )
            )
    scored.sort(key=lambda x: -x[0])
    seen = set()
    out: List[Dict[str, str]] = []
    for _s, rec in scored:
        key = rec["id"] + rec["snippet"][:40]
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def catalog_from_programs(items: Sequence[Any], lang: str = "CHN") -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for it in items or []:
        do_proc = str(getattr(it, "do_proc", "") or "").strip()
        if not do_proc:
            continue
        key = do_proc.upper()
        if key in seen:
            continue
        seen.add(key)
        title = ""
        get_title = getattr(it, "get_title", None)
        if callable(get_title):
            title = str(get_title(lang) or "")
        if not title:
            title = str(getattr(it, "chn_title", "") or getattr(it, "eng_title", "") or do_proc)
        out.append(
            {
                "do_proc": do_proc,
                "title": title,
                "work_file": str(getattr(it, "work_file", "") or ""),
                "other_title": str(getattr(it, "other_title", "") or ""),
            }
        )
    return out


def _norm_label(text: str) -> str:
    return re.sub(r"[\s\-_/\.]+", "", (text or "").lower())


_CODE_TOKEN_RE = r"[A-Za-z0-9][A-Za-z0-9._/\-]{2,}"

_QUERY_STOP_WORDS = {
    "OPEN",
    "QUERY",
    "SEARCH",
    "FIND",
    "SHOW",
    "VIEW",
    "TAB",
    "AI",
    "PDF",
    "DOC",
    "DOCX",
    "XLS",
    "XLSX",
    "CSV",
    "JSON",
    "查詢",
    "查一下",
    "搜尋",
    "找尋",
    "查找",
    "開啟",
    "打開",
    "進入",
    "顯示",
    "看看",
    "STOCK",
    "STK",
    "INVENTORY",
    "ACCOUNT",
    "ACC",
    "CUSTVEND",
    "CUST",
    "VEND",
    "存貨",
    "庫存",
    "賬戶",
    "帳戶",
    "顧客",
    "客戶",
    "供應商",
    "廠商",
}


def _strip_for_program_match(msg: str, *tokens: str) -> str:
    s = (msg or "").strip()
    for tok in tokens:
        t = (tok or "").strip()
        if not t:
            continue
        s = re.sub(re.escape(t), " ", s, flags=re.I)
    s = re.sub(
        r"^(?:請|幫我|幫忙|麻烦|麻煩|能否|可以|想要|我要|給我|幫)\s*",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"^(?:open|show|view|display|go to|goto)\s+",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"^(?:開啟|打開|進入|顯示|看|查看|浏览|瀏覽)\s*", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" ，,。;；:")


def _extract_code_tokens(msg: str) -> List[str]:
    return re.findall(_CODE_TOKEN_RE, msg or "")


def _pick_query_code(msg: str) -> str:
    for tok in reversed(_extract_code_tokens(msg)):
        if tok.upper() in _QUERY_STOP_WORDS:
            continue
        if tok.isdigit() and len(tok) < 4:
            continue
        return tok.strip()
    return ""


def _looks_like_search_request(msg: str) -> bool:
    """作業工具列「搜尋／找尋」：在主檔定位紀錄（非開啟查詢介面）。"""
    s = (msg or "").strip()
    if not s or re.search(r"文件|檔案|document", s, re.I):
        return False
    if re.search(r"\bfind\b|\bsearch\b|\blookup\b", s, re.I):
        return True
    if re.search(r"搜尋|找尋|查找|找一下", s, re.I):
        return True
    # 「找 CODE」但排除「找一下查詢」類已由上方涵蓋
    if re.search(r"找\s*[A-Za-z0-9]", s, re.I) and not re.search(
        r"查詢|query", s, re.I
    ):
        return True
    return False


def _looks_like_query_request(msg: str) -> bool:
    s = (msg or "").strip()
    if not s or re.search(r"文件|檔案|document", s, re.I):
        return False
    # 更改／新增等 CRUD、以及 find／搜尋 優先，不走查詢
    if _looks_like_crud_request(s):
        return False
    if _looks_like_search_request(s):
        return False
    if re.search(r"查詢|query", s, re.I):
        return True
    if re.search(r"查一下|查查看|查下|幫我查|帮我查|查查看", s, re.I):
        return True
    if re.search(r"(?:顧客|客戶|供應商|廠商|存貨|庫存|stock|inventory).{0,20}(?:查|查詢|資料|交易|明細)", s, re.I):
        return True
    if re.search(r"(?:查|看看|顯示|找一下|show|view)\s*[A-Za-z0-9]", s, re.I):
        return True
    if re.search(r"找\s+[A-Za-z0-9]", s, re.I) and re.search(
        r"顧客|客戶|供應商|廠商|存貨|庫存|查詢|stock", s, re.I
    ):
        return True
    # 避免 find／search 等動詞被當成「編號 + 顧客」口語查詢
    if re.search(
        r"[A-Za-z0-9]{2,}.{0,12}(?:的)?(?:顧客|供應商|客戶|存貨|庫存|資料)", s, re.I
    ):
        head = re.match(r"^\s*([A-Za-z0-9_\-]+)", s)
        if head and head.group(1).upper() not in _QUERY_STOP_WORDS:
            return True
    if re.search(r"(?:stock|inventory|存貨|庫存)\s*(?:查詢|query)\s*[:：]?\s*[A-Za-z0-9]", s, re.I):
        return True
    if re.search(r"(?:stock|inventory|存貨|庫存)\s+查詢\s*[A-Za-z0-9]", s, re.I):
        return True
    if re.search(r"[\u4e00-\u9fff\-]+查詢\s*[:：]?\s*[A-Za-z0-9]", s):
        return True
    if re.search(r"(?:開啟|open|打開).{0,30}查詢\s*[:：]?\s*[A-Za-z0-9]", s, re.I):
        return True
    if re.search(r"查詢\s*[A-Za-z0-9]", s, re.I):
        return True
    return False


def _match_master_program(
    catalog: Sequence[Dict[str, str]],
    text: str,
    *,
    keyword: str = "",
) -> Optional[Dict[str, str]]:
    """配對主檔作業（排除「查詢」類），例如 stock → STOCK 資料表而非存貨查詢。"""
    strip_words = [
        keyword,
        "更改",
        "修改",
        "編輯",
        "新增",
        "刪除",
        "複製",
        "離開",
        "edit",
        "add",
        "delete",
        "copy",
        "new",
        "record",
        "exit",
    ]
    q = _strip_for_program_match(text, *strip_words)
    if not q:
        q = (text or "").strip()
    qu = q.upper().replace(" ", "")
    ql = q.lower()
    qn = _norm_label(q)
    wants_stock = bool(re.search(r"stock|inventory|stk|存貨|庫存", q, re.I))
    wants_party = bool(re.search(r"顧客|客戶|供應商|廠商|custvend|cust|vend", q, re.I))
    best: Optional[Tuple[int, Dict[str, str]]] = None
    for it in catalog:
        title = it.get("title") or ""
        other = it.get("other_title") or ""
        work = (it.get("work_file") or "").upper()
        proc = (it.get("do_proc") or "").upper()
        blob = f"{title} {other}"
        is_query = bool(re.search(r"查詢|QUERY", blob, re.I)) or "QUERY" in proc
        score = 0
        if work and work in qu:
            score += 100
        if proc and proc in qu:
            score += 80
        if wants_stock and work == "STOCK":
            score += 120
        if wants_party and work == "CUSTVEND":
            score += 120
        for label in (title, other):
            if not label:
                continue
            if label.lower() in ql:
                score += 50
            ln = _norm_label(label)
            if len(ln) >= 2 and ln in qn:
                score += 40
        if is_query:
            score -= 100
        if score > 0 and (best is None or score > best[0]):
            best = (score, it)
    if best and best[0] >= 40:
        return best[1]
    hit = match_program(catalog, q, exclude_tokens=[keyword] if keyword else None)
    if hit:
        other = hit.get("other_title") or ""
        title = hit.get("title") or ""
        proc = (hit.get("do_proc") or "").upper()
        if re.search(r"查詢|QUERY", f"{title} {other}", re.I) or "QUERY" in proc:
            # 再試一次：只挑非查詢且同 work_file
            work = (hit.get("work_file") or "").upper()
            if work:
                for it in catalog:
                    blob = f"{it.get('title') or ''} {it.get('other_title') or ''}"
                    if (it.get("work_file") or "").upper() != work:
                        continue
                    if re.search(r"查詢|QUERY", blob, re.I):
                        continue
                    return it
        return hit
    return None


def _extract_crud_keyword(msg: str) -> str:
    s = (msg or "").strip()
    quoted = re.search(r"[「『\"']([^」』\"']+)[」』\"']", s)
    if quoted:
        return quoted.group(1).strip()
    code = _CODE_TOKEN_RE
    for pat in [
        rf"(?:更改|修改|編輯|新增|刪除|複製|edit|add|delete|copy)\s*(?:stock|inventory|stk|存貨|庫存|顧客|客戶|供應商)?\s*[:：]?\s*({code})",
        rf"(?:stock|inventory|stk|存貨|庫存|顧客|客戶|供應商)\s*[:：]?\s*({code})",
        rf"(?:編號|號碼|key|no\.?|#)\s*[:：]?\s*({code})",
    ]:
        m = re.search(pat, s, re.I)
        if m:
            kw = m.group(1).strip()
            if kw.upper() not in _QUERY_STOP_WORDS:
                return kw
    return _pick_query_code(s)


def _looks_like_crud_request(msg: str) -> Optional[Tuple[str, str]]:
    """若為 CRUD 指令，回傳 (act, label)；否則 None。"""
    crud_map = [
        (r"新增|add\b|new\s+record", "add", "新增"),
        (r"複製|copy\b", "copy", "複製"),
        (r"刪除|delete\b", "delete", "刪除"),
        (r"更改|修改|編輯|edit\b", "edit", "更改"),
        (r"離開|exit\b", "exit", "離開"),
    ]
    for pat, act, label in crud_map:
        if re.search(pat, msg or "", re.I):
            return act, label
    return None


def _match_query_program(
    catalog: Sequence[Dict[str, str]], text: str, keyword: str = ""
) -> Optional[Dict[str, str]]:
    from core.query_registry import match_query_program as registry_match

    return registry_match(
        catalog, text, keyword, match_program_fn=match_program
    )


def match_program(
    catalog: Sequence[Dict[str, str]],
    text: str,
    *,
    exclude_tokens: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, str]]:
    q = _strip_for_program_match(text, *(exclude_tokens or []))
    if not q:
        return None
    qu = q.upper()
    ql = q.lower()
    qn = _norm_label(q)
    best: Optional[Tuple[int, Dict[str, str]]] = None
    for it in catalog:
        proc = (it.get("do_proc") or "").upper()
        title = it.get("title") or ""
        other = it.get("other_title") or ""
        work = (it.get("work_file") or "").upper()
        score = 0
        if proc and proc in qu.replace(" ", ""):
            score += 80
        if work and work in qu.replace(" ", ""):
            score += 70
        for label in (title, other):
            if not label:
                continue
            if label.lower() in ql:
                score += 90
            ln = _norm_label(label)
            if len(ln) >= 3 and ln in qn:
                score += 88
        for tok in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{3,}", q):
            tl = tok.lower()
            tu = tok.upper()
            if tl in title.lower() or tl in other.lower():
                score += 25
            if tu in proc or tu in work:
                score += 25
        if score > 0 and (best is None or score > best[0]):
            best = (score, it)
    if best and best[0] >= 25:
        return best[1]
    return None


def _llm_enabled_for(base_dir: str = "", user_no: str = "") -> bool:
    if base_dir and user_no:
        from core.ai_settings import llm_enabled_for_user

        return llm_enabled_for_user(base_dir, user_no)
    return bool(
        (os.environ.get("WOLEE_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    )


def _llm_enabled() -> bool:
    return _llm_enabled_for()


_LLM_LAST_ERROR = ""


def _llm_last_error() -> str:
    return (_LLM_LAST_ERROR or "").strip()


def _extract_chat_completion_text(data: Any) -> str:
    """從 OpenAI／OpenRouter chat.completion JSON 取出可顯示文字。"""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    msg = choices[0].get("message") or {}
    if not isinstance(msg, dict):
        # 少數相容：choice.text
        return str(choices[0].get("text") or "").strip()
    content = msg.get("content")
    if isinstance(content, list):
        # 多段 content（部分 provider）
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text") or block.get("content") or ""
                if t:
                    parts.append(str(t))
        content = "\n".join(parts)
    text = str(content or "").strip()
    if text:
        return text
    # 少數模型只回 refusal
    refusal = str(msg.get("refusal") or "").strip()
    if refusal:
        return refusal
    return ""


def _call_llm(
    messages: List[Dict[str, str]],
    *,
    base_dir: str = "",
    user_no: str = "",
    timeout: int = 90,
) -> Optional[str]:
    """
    呼叫 Chat Completions。成功回傳文字；失敗回傳 None（錯誤見 _llm_last_error）。
    """
    global _LLM_LAST_ERROR
    _LLM_LAST_ERROR = ""
    if base_dir and user_no:
        from core.ai_settings import resolve_llm_config

        key, base, model, _src = resolve_llm_config(base_dir, user_no)
    else:
        key = (os.environ.get("WOLEE_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
        base = (os.environ.get("WOLEE_AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        model = (os.environ.get("WOLEE_AI_MODEL") or "gpt-4o-mini").strip()
    if not key:
        _LLM_LAST_ERROR = "missing api key"
        return None
    payload = {
        "model": model,
        "temperature": 0.4,
        "messages": messages,
    }
    url = f"{base.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        # OpenRouter 建議標頭；其他端點通常可忽略
        "HTTP-Referer": "https://wolee.local",
        "X-Title": "WoleeWeb AI",
    }
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=max(30, int(timeout or 90))) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # 部分 provider 在 JSON 前塞空白行
        raw_stripped = (raw or "").lstrip()
        data = json.loads(raw_stripped)
        text = _extract_chat_completion_text(data)
        if text:
            return text
        # 空 content：記錄 finish_reason 方便排查
        choice0 = ((data.get("choices") or [{}])[0]) if isinstance(data, dict) else {}
        fr = ""
        if isinstance(choice0, dict):
            fr = str(choice0.get("finish_reason") or choice0.get("native_finish_reason") or "")
        _LLM_LAST_ERROR = f"empty content from model ({model})" + (f", finish={fr}" if fr else "")
        return None
    except Exception as ex:
        try:
            import urllib.error

            if isinstance(ex, urllib.error.HTTPError):
                body = ""
                try:
                    body = ex.read().decode("utf-8", errors="replace")[:400]
                except Exception:
                    body = ""
                _LLM_LAST_ERROR = f"HTTP {ex.code}: {body or ex.reason}"
            else:
                _LLM_LAST_ERROR = str(ex) or type(ex).__name__
        except Exception:
            _LLM_LAST_ERROR = str(ex) or type(ex).__name__
        return None


def _parse_llm_payload(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    s = (text or "").strip()
    if not s:
        return "", []
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        m2 = re.search(r"(\{\s*\"reply\".*\})", s, re.S)
        blob = m2.group(1) if m2 else None
    if blob:
        try:
            obj = json.loads(blob)
            reply = str(obj.get("reply") or "").strip()
            actions = obj.get("actions") if isinstance(obj.get("actions"), list) else []
            clean = [a for a in actions if isinstance(a, dict) and a.get("type")]
            # reply 空白時仍回傳原文，避免日常問答被吃掉
            return (reply if reply else s), clean
        except Exception:
            pass
    return s, []


def _daily_system_prompt(lang: str = "CHN") -> str:
    chn = str(lang or "").upper().startswith("C")
    if chn:
        return (
            "你是企業管理系統的中文助理，請用繁體中文清楚回答使用者的日常問題。"
            "直接給出有用的答案，不要輸出 JSON，不要只重複能力說明。"
            "若不確定即時資料（如天氣），請誠實說明並提供可行建議。"
        )
    return (
        "You are a helpful assistant for an enterprise system. "
        "Answer everyday questions clearly in plain text. Do not output JSON."
    )


def _ops_system_prompt(
    *,
    catalog_txt: str,
    active_do_proc: str,
    doc_txt: str,
) -> str:
    return (
        "你是企業管理系統的中文助理。優先用繁體中文直接回答日常問題、根據私人文件摘錄作答；"
        "只有在使用者明確要求開啟作業、查詢、搜尋、新增／更改／刪除／複製／離開／列印等系統操作時，"
        "才輸出 JSON："
        '{"reply":"...","actions":[{"type":"open_work","do_proc":"...","title":"..."},'
        '{"type":"close_tab"},{"type":"close_all_tabs"},'
        '{"type":"add"},{"type":"edit"},{"type":"delete"},{"type":"copy"},'
        '{"type":"exit"},{"type":"print","mode":"preview"},{"type":"query","keyword":"..."},'
        '{"type":"search","keyword":"..."}]}。'
        "日常問答請直接寫在 reply（或純文字），不要空回覆。"
        "查詢請帶 keyword（編號）。更改／編輯請用 edit 並可帶 keyword："
        "先 open_work（主檔如 STOCK），再 search，再 edit。"
        "type 必須是以上之一。不要捏造 do_proc。可用作業清單：\n"
        f"{catalog_txt}\n目前作業:{active_do_proc or '無'}\n私人文件摘錄：\n{doc_txt}"
    )


def _build_llm_history(history: Optional[Sequence[Dict[str, str]]]) -> List[Dict[str, str]]:
    hist: List[Dict[str, str]] = []
    for h in list(history or [])[-8:]:
        role = "assistant" if str(h.get("role")) == "assistant" else "user"
        hist.append({"role": role, "content": str(h.get("content") or "")[:2000]})
    return hist


def _ask_llm_for_chat(
    *,
    msg: str,
    history: Optional[Sequence[Dict[str, str]]],
    catalog: Sequence[Dict[str, str]],
    active_do_proc: str,
    sources: Sequence[Dict[str, Any]],
    base_dir: str,
    user_no: str,
    lang: str,
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """
    回傳 (reply, actions, error_message)。
    先用完整助理提示；若空回應再以日常問答提示重試一次。
    """
    cat_txt = "\n".join(
        f"- {c.get('title')} ({c.get('do_proc')}, 表:{c.get('work_file')})"
        for c in list(catalog)[:80]
    )
    doc_txt = "\n\n".join(f"【{s['name']}】{s['snippet']}" for s in sources) or "（無私人文件命中）"
    hist = _build_llm_history(history)
    sys_prompt = _ops_system_prompt(
        catalog_txt=cat_txt,
        active_do_proc=active_do_proc,
        doc_txt=doc_txt,
    )
    raw = _call_llm(
        [{"role": "system", "content": sys_prompt}] + hist + [{"role": "user", "content": msg}],
        base_dir=base_dir,
        user_no=user_no,
    )
    if raw:
        reply, actions = _parse_llm_payload(raw)
        if reply:
            return reply, actions, None

    # 空回應／解析失敗：改以純日常問答提示重試
    raw2 = _call_llm(
        [
            {"role": "system", "content": _daily_system_prompt(lang)},
            *hist[-4:],
            {"role": "user", "content": msg},
        ],
        base_dir=base_dir,
        user_no=user_no,
    )
    if raw2:
        reply2, actions2 = _parse_llm_payload(raw2)
        if reply2:
            return reply2, actions2, None

    err = _llm_last_error() or "empty response"
    return "", [], err


def _extract_query_keyword(msg: str) -> str:
    s = (msg or "").strip()
    quoted = re.search(r"[「『\"']([^」』\"']+)[」』\"']", s)
    if quoted:
        return quoted.group(1).strip()
    code = _CODE_TOKEN_RE
    for pat in [
        rf"(?:stock|inventory|stk|存貨|庫存)\s*(?:查詢|query)?\s*[:：]?\s*({code})",
        rf"(?:account|acc|賬戶|帳戶)\s*(?:查詢|query)?\s*[:：]?\s*({code})",
        rf"(?:顧客\s*[-/]?\s*供應商|客戶\s*[-/]?\s*廠商|custvend|顧客|客戶|供應商|廠商)\s*(?:查詢|query)?\s*[:：]?\s*({code})",
        rf"[\u4e00-\u9fff\-/]+查詢\s*[:：]?\s*({code})",
        rf"(?:開啟|open|打開|進入|顯示|看|show|view)\s*[\u4e00-\u9fff\-/\s]*查詢?\s*[:：]?\s*({code})",
        rf"(?:查詢|query)\s*[:：]?\s*({code})",
        rf"(?:查詢|query)({code})",
        rf"(?:搜尋|找尋|查找|search|find|lookup|查一下|查查看|幫我查|帮我查|查下|查|看看|顯示|找一下|找|show|view)\s*({code})",
        rf"({code})\s*(?:的)?(?:顧客|客戶|供應商|廠商|存貨|庫存|資料|交易|明細)",
        rf"(?:編號|號碼|單號|key|no\.?|#)\s*[:：]?\s*({code})",
        rf"(?:for|about)\s+({code})",
    ]:
        m = re.search(pat, s, re.I)
        if m:
            kw = m.group(1).strip()
            if kw.upper() not in _QUERY_STOP_WORDS:
                return kw
    # 標籤與編號緊貼：顧客-供應商GSC33SCRRC
    glued = re.search(
        rf"(?:顧客|客戶|供應商|廠商|stock|inventory|account|acc|存貨|庫存|賬戶|帳戶)\s*[-/]?\s*(?:供應商|廠商)?\s*({code})\b",
        s,
        re.I,
    )
    if glued:
        kw = glued.group(1).strip()
        if kw.upper() not in _QUERY_STOP_WORDS:
            return kw
    picked = _pick_query_code(s)
    if picked:
        return picked
    return _extract_keyword_after_verb(s, r"查詢|query|搜尋|找尋|查找|search|find|查", None)


def _extract_keyword_after_verb(
    msg: str, verb_pat: str, hit: Optional[Dict[str, str]]
) -> str:
    s = (msg or "").strip()
    quoted = re.search(r"[「『\"']([^」』\"']+)[」』\"']", s)
    if quoted:
        return quoted.group(1).strip()
    m = re.search(verb_pat, s, re.I)
    rest = s[m.end() :] if m else s
    rest = re.sub(r"^[:：\s]+", "", rest)
    if hit:
        for part in (hit.get("title"), hit.get("do_proc"), hit.get("work_file")):
            if part:
                rest = re.sub(re.escape(str(part)), " ", rest, flags=re.I)
    rest = re.sub(r"請|幫我|帮我|幫忙|麻烦|麻煩", " ", rest)
    rest = re.sub(
        r"資料表|作業|記錄|紀錄|的資料|查詢|查一下|顧客|客戶|供應商|廠商",
        " ",
        rest,
    )
    return re.sub(r"\s+", " ", rest).strip(" 。，,")


def _looks_like_analysis_request(msg: str) -> bool:
    return bool(
        re.search(r"分析|統計|summary|summari|analy", msg or "", re.I)
    )


def _looks_like_related_search_request(msg: str) -> bool:
    s = (msg or "").strip()
    return bool(
        re.search(r"相關資料|所有相關|全部相關|全部資料|全都資料", s, re.I)
        or (
            re.search(r"編號|關鍵字|keyword", s, re.I)
            and re.search(r"搜尋|查詢|尋找|找出|search|find", s, re.I)
        )
    )


def _looks_like_excel_export_request(msg: str) -> bool:
    s = (msg or "").strip()
    return bool(re.search(r"匯出|導出|export", s, re.I) and re.search(r"excel|xlsx", s, re.I))


# 相關資料可選欄位：id → (中文名列, 英文名列, 預設顯示)
_RELATED_FIELD_CATALOG: Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...], bool], ...] = (
    ("date", ("日期",), ("date", "dates"), True),
    ("stk_code", ("貨品", "貨品編號"), ("stock", "stock code", "item code"), True),
    ("item", ("項目", "說明", "品名"), ("item", "desc", "description"), False),
    ("unit", ("單位",), ("unit", "uom"), False),
    ("qty", ("數量",), ("qty", "quantity", "quantities"), True),
    ("price", ("單價",), ("price", "unit price"), True),
    ("amount", ("金額",), ("amount", "amt"), True),
)

_RELATED_DEFAULT_FIELDS: Tuple[str, ...] = tuple(
    fid for fid, _c, _e, default in _RELATED_FIELD_CATALOG if default
)


def _related_field_label(field_id: str, *, chn: bool = True) -> str:
    for fid, chn_labs, eng_labs, _d in _RELATED_FIELD_CATALOG:
        if fid == field_id:
            return chn_labs[0] if chn else eng_labs[0]
    return field_id


def _match_related_field_ids_in_text(blob: str) -> List[str]:
    """從一段文字辨識欄位 id（較長標籤優先）。"""
    s = (blob or "").strip()
    if not s:
        return []
    low = s.lower()
    pairs: List[Tuple[int, str, str]] = []
    for fid, chn_labs, eng_labs, _d in _RELATED_FIELD_CATALOG:
        for lab in list(chn_labs) + list(eng_labs):
            pairs.append((len(lab), fid, lab))
    pairs.sort(key=lambda x: -x[0])
    found: List[str] = []
    seen = set()
    # 用佔位避免短標籤重複命中同一段
    work = s
    work_low = low
    for _n, fid, lab in pairs:
        if fid in seen:
            continue
        if re.fullmatch(r"[A-Za-z ]+", lab):
            pat = re.compile(rf"\b{re.escape(lab)}\b", re.I)
            if not pat.search(work_low):
                continue
            work_low = pat.sub(" ", work_low)
        else:
            if lab not in work:
                continue
            work = work.replace(lab, " ", 1)
        seen.add(fid)
        found.append(fid)
    return found


def _parse_related_column_options(msg: str) -> Dict[str, Any]:
    """
    解析「不要／增加」欄位選項。
    例：不要單價，增加項目、單位
    回傳 fields（最終欄位 id 清單）、exclude、include。
    """
    s = (msg or "").strip()
    fields = list(_RELATED_DEFAULT_FIELDS)
    exclude: List[str] = []
    include: List[str] = []

    # 排除：不要／不含／排除／略過／不列 …
    for m in re.finditer(
        r"(?:不要|不含|排除|略過|無|不列)\s*(?:列出|顯示|匯出|包含)?\s*([^。；;\n增加加上加入要有]*)",
        s,
        re.I,
    ):
        chunk = m.group(1) or ""
        # 截斷到下一個「增加」類動詞之前
        chunk = re.split(r"增加|加上|加入|要有|匯出|導出|export", chunk, maxsplit=1)[0]
        for fid in _match_related_field_ids_in_text(chunk):
            if fid not in exclude:
                exclude.append(fid)

    # 增加：增加／加上／加入／要有 …
    for m in re.finditer(
        r"(?:增加|加上|加入|要有)\s*([^。；;\n不要不含排除略過]*)",
        s,
        re.I,
    ):
        chunk = m.group(1) or ""
        chunk = re.split(r"不要|不含|排除|略過|匯出|導出|export", chunk, maxsplit=1)[0]
        for fid in _match_related_field_ids_in_text(chunk):
            if fid not in include:
                include.append(fid)

    # 英文：without X / exclude X / add X / include X
    for m in re.finditer(
        r"(?:without|exclude|omit|hide|no)\s+([^.\n;]+)",
        s,
        re.I,
    ):
        for fid in _match_related_field_ids_in_text(m.group(1) or ""):
            if fid not in exclude:
                exclude.append(fid)
    for m in re.finditer(
        r"(?:add|include|with)\s+([^.\n;]+)",
        s,
        re.I,
    ):
        for fid in _match_related_field_ids_in_text(m.group(1) or ""):
            if fid not in include:
                include.append(fid)

    for fid in exclude:
        while fid in fields:
            fields.remove(fid)
    for fid in include:
        if fid not in fields:
            # 插入到合理位置
            order = [x[0] for x in _RELATED_FIELD_CATALOG]
            fields.append(fid)
            fields.sort(key=lambda x: order.index(x) if x in order else 99)

    return {
        "fields": fields,
        "exclude": exclude,
        "include": include,
        "include_date": "date" in fields,
        "include_qty": "qty" in fields,
    }


def _extract_related_search_keyword(msg: str) -> str:
    s = (msg or "").strip()
    quoted = re.search(r"[「『\"']([^」』\"']+)[」』\"']", s)
    if quoted:
        return quoted.group(1).strip()
    for pat in [
        r"(?:編號|號碼|單號)\s*[:：]?\s*([A-Za-z0-9._/\-]+)",
        r"(?:關鍵字|keyword)\s*[:：]?\s*([^\s，。；;]+)",
        r"(?:搜尋|查詢|尋找|找出|search|find)\s*[:：]?\s*([^\s，。；;]+)",
    ]:
        m = re.search(pat, s, re.I)
        if m:
            return m.group(1).strip()
    tokens = re.findall(r"[A-Za-z0-9._/\-]{2,}|[\u4e00-\u9fff]{2,}", s)
    stop = {
        "相關資料",
        "所有相關",
        "全部相關",
        "全部資料",
        "編號",
        "關鍵字",
        "搜尋",
        "查詢",
        "尋找",
        "找出",
        "資料",
        "列出",
        "匯出",
        "導出",
        "日期",
        "數量",
        "單價",
        "金額",
        "項目",
        "單位",
        "說明",
        "品名",
        "貨品",
        "增加",
        "加上",
        "加入",
        "不要",
        "excel",
        "xlsx",
    }
    for tok in reversed(tokens):
        if tok.lower() in stop or tok in stop:
            continue
        return tok
    return ""


def _summarize_needs(
    message: str,
    history: Optional[Sequence[Dict[str, str]]],
    sources: Sequence[Dict[str, str]],
    related_summary: str = "",
    lang: str = "CHN",
) -> str:
    chn = str(lang or "").upper().startswith("C")
    texts = [str(h.get("content") or "") for h in list(history or [])[-8:]] + [message]
    blob = "\n".join(texts)
    groups = [
        ("日常問答", r"日常|問題|日期|計算|help|today|now"),
        ("文件搜尋", r"文件|檔案|pdf|docx|xlsx|上傳"),
        ("需求分析", r"分析|統計|summary|analy"),
        ("系統操作", r"開啟|關閉|新增|更改|刪除|複製|離開|列印|查詢|搜尋"),
        ("資料關聯搜尋", r"相關資料|編號|關鍵字|所有相關"),
    ]
    hits = [name for name, pat in groups if re.search(pat, blob, re.I)]
    doc_names = []
    seen = set()
    for s in sources or []:
        name = str(s.get("name") or "")
        if name and name not in seen:
            seen.add(name)
            doc_names.append(name)
    if chn:
        parts = [
            "需求分析：",
            f"• 最近對話訊息：{len(texts)} 段",
            f"• 偵測到的需求類別：{'、'.join(hits) if hits else '一般問答'}",
            f"• 命中的私人文件：{len(doc_names)} 份"
            + (f"（{'、'.join(doc_names[:3])}）" if doc_names else ""),
        ]
        if related_summary:
            parts.append(related_summary)
        parts.append("如要我深入統計，可直接說「分析這些文件」或「統計這個編號的相關資料」。")
        return "\n".join(parts)
    parts = [
        "Needs analysis:",
        f"- Recent messages: {len(texts)}",
        f"- Detected categories: {', '.join(hits) if hits else 'general Q&A'}",
        f"- Matched private documents: {len(doc_names)}",
    ]
    if related_summary:
        parts.append(related_summary)
    return "\n".join(parts)


def _should_open_work_tab(active_do_proc: str, do_proc: str) -> bool:
    """目標作業與目前畫面作業不同時，需開啟或切換 TAB。"""
    target = str(do_proc or "").strip().upper()
    if not target:
        return False
    active = str(active_do_proc or "").strip().upper()
    return active != target


def parse_local_intent(
    message: str,
    catalog: Sequence[Dict[str, str]],
    *,
    active_do_proc: str = "",
    lang: str = "CHN",
) -> Tuple[str, List[Dict[str, Any]]]:
    """規則意圖：開啟作業、關閉 TAB、CRUD、列印、查詢、搜尋。"""
    msg = (message or "").strip()
    if not msg:
        return "", []
    # 「所有相關資料」交由 related_search，勿當成一般查詢／搜尋
    if _looks_like_related_search_request(msg):
        return "", []
    low = msg.lower()
    actions: List[Dict[str, Any]] = []

    def _chn() -> bool:
        return str(lang or "").upper().startswith("C")

    # 關閉
    if re.search(r"關閉全部|close all", msg, re.I):
        actions.append({"type": "close_all_tabs"})
        return ("已關閉所有分頁。" if _chn() else "Closed all tabs."), actions
    if re.search(r"關閉\s*(tab|分頁|作業)|close\s+tab", msg, re.I):
        hit = match_program(catalog, msg)
        actions.append(
            {
                "type": "close_tab",
                "do_proc": (hit or {}).get("do_proc") or active_do_proc or "",
                "title": (hit or {}).get("title") or "",
            }
        )
        return ("已關閉分頁。" if _chn() else "Closed the tab."), actions

    # 列印 / 預覽
    if re.search(r"列印預覽|預覽|print\s*preview|preview", msg, re.I) or re.search(
        r"列印|print", msg, re.I
    ):
        hit = match_program(catalog, msg)
        do_proc = (hit or {}).get("do_proc") or active_do_proc or ""
        if hit and _should_open_work_tab(active_do_proc, do_proc):
            actions.append(
                {"type": "open_work", "do_proc": hit["do_proc"], "title": hit.get("title") or ""}
            )
        actions.append({"type": "print", "mode": "preview", "do_proc": do_proc})
        return (
            "將開啟列印預覽（預設資料列表）。" if _chn() else "Opening print preview.",
            actions,
        )

    # CRUD / 離開（優先於查詢：更改 stock A01 → 開 STOCK 主檔、搜尋、更改）
    crud = _looks_like_crud_request(msg)
    if crud:
        act, label = crud
        keyword = "" if act == "exit" else _extract_crud_keyword(msg)
        hit = _match_master_program(catalog, msg, keyword=keyword)
        do_proc = (hit or {}).get("do_proc") or active_do_proc or ""
        if hit and act != "exit":
            actions.append(
                {
                    "type": "open_work",
                    "do_proc": hit["do_proc"],
                    "title": hit.get("title") or "",
                }
            )
        if keyword and act in {"edit", "copy", "delete"}:
            actions.append(
                {"type": "search", "keyword": keyword, "do_proc": do_proc}
            )
        actions.append({"type": act, "do_proc": do_proc})
        if keyword and act != "exit":
            title = (hit or {}).get("title") or do_proc or ""
            if _chn():
                if title:
                    return (
                        f"將開啟「{title}」，搜尋「{keyword}」並執行「{label}」。",
                        actions,
                    )
                return (f"將搜尋「{keyword}」並執行「{label}」。", actions)
            return (f"Will open, search {keyword}, then {act}.", actions)
        return (f"將執行「{label}」。" if _chn() else f"Running {act}."), actions

    # 作業工具列「搜尋／找尋」：定位紀錄，不過濾（優先於查詢）
    if _looks_like_search_request(msg):
        keyword = _extract_query_keyword(msg) or _extract_keyword_after_verb(
            msg, r"搜尋|找尋|查找|search|find|lookup|找", None
        )
        # 去掉作業名稱後再取編號（find 顧客-供應商GSC33SCRRC）
        if not keyword or keyword.upper() in _QUERY_STOP_WORDS:
            keyword = _extract_query_keyword(
                re.sub(
                    r"顧客\s*[-/]?\s*供應商|客戶\s*[-/]?\s*廠商|custvend|customer|vendor",
                    " ",
                    msg,
                    flags=re.I,
                )
            ) or keyword
        hit = _match_master_program(catalog, msg, keyword=keyword) or match_program(
            catalog,
            msg,
            exclude_tokens=[keyword] if keyword else None,
        )
        do_proc = (hit or {}).get("do_proc") or active_do_proc or ""
        if hit and _should_open_work_tab(active_do_proc, do_proc):
            actions.append(
                {"type": "open_work", "do_proc": hit["do_proc"], "title": hit.get("title") or ""}
            )
        actions.append({"type": "search", "keyword": keyword, "do_proc": do_proc})
        if keyword:
            reply = f"將搜尋「{keyword}」。" if _chn() else f"Searching for {keyword}."
        else:
            reply = "將執行搜尋。" if _chn() else "Running search."
        return reply, actions

    # 查詢（含口語：查一下、看看、顯示、open stock 查詢A02）
    if _looks_like_query_request(msg):
        keyword = _extract_query_keyword(msg)
        hit = _match_query_program(catalog, msg, keyword)
        do_proc = (hit or {}).get("do_proc") or active_do_proc or ""
        if hit and _should_open_work_tab(active_do_proc, do_proc):
            actions.append(
                {"type": "open_work", "do_proc": hit["do_proc"], "title": hit.get("title") or ""}
            )
        from core.query_registry import build_query_action

        actions.append(build_query_action(do_proc, keyword, catalog_item=hit))
        if keyword:
            return (
                (f"將開啟查詢「{keyword}」。" if _chn() else f"Opening query for {keyword}."),
                actions,
            )
        return ("將開啟查詢。" if _chn() else "Opening query."), actions

    # 開啟作業 / 資料表
    if re.search(
        r"開啟|打開|進入|open\b|show\b|view\b|display\b|看看|顯示|查看|浏览|瀏覽",
        msg,
        re.I,
    ):
        keyword = _extract_query_keyword(msg)
        if keyword and _looks_like_query_request(msg):
            hit = _match_query_program(catalog, msg, keyword)
            do_proc = (hit or {}).get("do_proc") or active_do_proc or ""
            if hit:
                actions.append(
                    {
                        "type": "open_work",
                        "do_proc": hit["do_proc"],
                        "title": hit.get("title") or "",
                    }
                )
            from core.query_registry import build_query_action

            actions.append(
                build_query_action(do_proc, keyword, catalog_item=hit)
            )
            return (
                f"將開啟查詢「{keyword}」。" if _chn() else f"Opening query for {keyword}.",
                actions,
            )
        hit = match_program(catalog, msg)
        if hit:
            actions.append(
                {"type": "open_work", "do_proc": hit["do_proc"], "title": hit.get("title") or ""}
            )
            return (
                f"正在開啟「{hit.get('title') or hit['do_proc']}」。"
                if _chn()
                else f"Opening {hit.get('title') or hit['do_proc']}.",
                actions,
            )

    # 沒有「開啟」字樣但明確點名作業
    hit = match_program(catalog, msg)
    if hit and len(msg) <= 24:
        actions.append(
            {"type": "open_work", "do_proc": hit["do_proc"], "title": hit.get("title") or ""}
        )
        return (
            f"正在開啟「{hit.get('title') or hit['do_proc']}」。"
            if _chn()
            else f"Opening {hit.get('title') or hit['do_proc']}.",
            actions,
        )
    return "", []


def _simple_daily_answer(message: str, lang: str) -> Optional[str]:
    msg = (message or "").strip()
    chn = str(lang or "").upper().startswith("C")
    if re.search(r"今天|日期|now|today|幾號", msg, re.I):
        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        return f"現在是 {now}。" if chn else f"It is {now}."
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*([+\-*/])\s*(-?\d+(?:\.\d+)?)", msg)
    if m:
        a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
        try:
            val = {"+": a + b, "-": a - b, "*": a * b, "/": a / b}[op]
            return f"計算結果：{val:g}" if chn else f"Result: {val:g}"
        except Exception:
            return "無法計算。" if chn else "Cannot calculate."
    if re.search(r"你能做|你可以|help|幫助|怎麼用|功能", msg, re.I):
        if chn:
            return (
                "我可以：解答日常問題；上傳私人文件並在文件中找資料；"
                "分析及統計您的需求；以及操作本系統，例如開啟資料表、關閉 TAB、"
                "新增／更改／刪除／複製／離開／列印（預覽，預設資料列表）／查詢／搜尋。\n"
                "您也可以輸入編號或關鍵字，要求我找出資料庫中的所有相關資料。\n"
                "口語範例：\n"
                "• 「開啟發票」「列印預覽」「搜尋 1001」\n"
                "• 「open 顧客-供應商查詢:GSC33SATAL1」\n"
                "• 「開啟顧客供應商查詢 GSC33SATAL1」\n"
                "• 「查一下 GSC33SATAL1」「顯示 GSC33SATAL1 的顧客資料」\n"
                "• 「找出編號 INV001 的所有相關資料」「分析這些需求」"
            )
        return (
            "I can answer questions, search uploaded files, analyze needs, and operate this "
            "system (open tables, close tabs, add/edit/delete/copy/exit/print/query/search)."
        )
    return None


def chat(
    *,
    base_dir: str,
    user_no: str,
    message: str,
    catalog: Sequence[Dict[str, str]],
    history: Optional[Sequence[Dict[str, str]]] = None,
    active_do_proc: str = "",
    lang: str = "CHN",
    backend: Optional[DbBackendBase] = None,
    table_name: str = "",
    related_search_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    msg = (message or "").strip()
    chn = str(lang or "").upper().startswith("C")
    if not msg:
        return {
            "reply": "請輸入問題或指令。" if chn else "Please enter a question.",
            "actions": [],
            "sources": [],
            "llm_enabled": _llm_enabled_for(base_dir, user_no),
        }

    sources = search_user_documents(base_dir, user_no, msg, limit=5)
    local_reply, actions = parse_local_intent(
        msg, catalog, active_do_proc=active_do_proc, lang=lang
    )

    related_data: Optional[Dict[str, Any]] = None
    col_opts = _parse_related_column_options(msg)
    related_fields = list(col_opts.get("fields") or _RELATED_DEFAULT_FIELDS)
    include_date = bool(col_opts.get("include_date", True))
    include_qty = bool(col_opts.get("include_qty", True))
    if _looks_like_related_search_request(msg):
        related_kw = _extract_related_search_keyword(msg)
        if not related_search_fn:
            related_data = {
                "summary": (
                    "目前無法執行資料庫相關搜尋。"
                    if chn
                    else "Related database search is not available."
                ),
                "matches": [],
                "query": related_kw,
            }
        elif related_kw:
            try:
                try:
                    related_data = related_search_fn(  # type: ignore[misc]
                        related_kw,
                        fields=related_fields,
                        include_date=include_date,
                        include_qty=include_qty,
                    )
                except TypeError:
                    try:
                        related_data = related_search_fn(  # type: ignore[misc]
                            related_kw,
                            include_date=include_date,
                            include_qty=include_qty,
                        )
                    except TypeError:
                        try:
                            related_data = related_search_fn(  # type: ignore[misc]
                                related_kw, include_date=include_date
                            )
                        except TypeError:
                            related_data = related_search_fn(related_kw)
            except Exception as ex:
                related_data = {
                    "summary": (
                        f"搜尋「{related_kw}」相關資料時發生錯誤：{ex}"
                        if chn
                        else f"Error searching related data for {related_kw}: {ex}"
                    ),
                    "matches": [],
                    "query": related_kw,
                }
        else:
            related_data = {
                "summary": (
                    "請提供要搜尋的編號或關鍵字。"
                    if chn
                    else "Please provide a code or keyword to search."
                ),
                "matches": [],
            }

    daily = _simple_daily_answer(msg, lang)
    llm_reply = ""
    llm_actions: List[Dict[str, Any]] = []
    llm_error: Optional[str] = None
    rel_summary = str((related_data or {}).get("summary") or "").strip()
    # 已有相關資料搜尋結果時，直接回報，避免 LLM 只回「正在查詢…」卻無內容
    skip_llm = bool(actions) or (
        related_data is not None and _looks_like_related_search_request(msg)
    )
    if _llm_enabled_for(base_dir, user_no) and not skip_llm:
        llm_reply, llm_actions, llm_error = _ask_llm_for_chat(
            msg=msg,
            history=history,
            catalog=catalog,
            active_do_proc=active_do_proc,
            sources=sources,
            base_dir=base_dir,
            user_no=user_no,
            lang=lang,
        )

    parts: List[str] = []
    if rel_summary and _looks_like_related_search_request(msg):
        parts.append(rel_summary)
    elif llm_reply:
        parts.append(llm_reply)
        if llm_actions:
            actions = llm_actions
    elif local_reply:
        parts.append(local_reply)
    elif daily:
        parts.append(daily)
    elif sources:
        parts.append("在您上傳的文件中找到：")
        for s in sources[:3]:
            parts.append(f"• {s['name']}：{s['snippet']}")
    elif rel_summary:
        parts.append(rel_summary)
    elif _llm_enabled_for(base_dir, user_no) and not skip_llm:
        # 已設定 Key 但模型空回／失敗：明確告知，勿落回罐頭能力說明
        if chn:
            parts.append("AI 暫時無法回覆此問題，請稍後再試一次。")
            if llm_error:
                parts.append(f"（詳細：{llm_error[:180]}）")
        else:
            parts.append("The AI could not answer just now. Please try again.")
            if llm_error:
                parts.append(f"(Detail: {llm_error[:180]})")
    else:
        parts.append(
            "我可以解答日常問題、搜尋您上傳的私人文件，並操作本系統"
            "（開啟資料表、關閉 TAB、新增／更改／刪除／複製／離開／列印預覽／查詢／搜尋），"
            "也可分析需求與統計相關資料。"
            if chn
            else "Ask me anything, search uploaded files, or operate this system."
        )
        if not _llm_enabled_for(base_dir, user_no):
            parts.append(
                "尚未設定 AI API Key；請按「AI 設定」輸入，或設定 WOLEE_AI_API_KEY。系統指令與文件搜尋仍可用。"
                if chn
                else "No AI API key. Use AI Settings or set WOLEE_AI_API_KEY. Commands and file search still work."
            )
    if rel_summary:
        joined = "\n".join(parts)
        if rel_summary not in joined:
            parts.append(rel_summary)
    if related_data is not None and _looks_like_related_search_request(msg) and _looks_like_excel_export_request(msg):
        export_kw = str((related_data or {}).get("query") or _extract_related_search_keyword(msg) or "").strip()
        if export_kw:
            actions.append(
                {
                    "type": "export_related_xlsx",
                    "keyword": export_kw,
                    "fields": related_fields,
                    "include_date": include_date,
                    "include_qty": include_qty,
                }
            )
            notes: List[str] = []
            excl = list(col_opts.get("exclude") or [])
            incl = list(col_opts.get("include") or [])
            if excl:
                notes.append(
                    "不含" + "、".join(_related_field_label(f, chn=chn) for f in excl)
                    if chn
                    else "without " + ", ".join(_related_field_label(f, chn=False) for f in excl)
                )
            if incl:
                notes.append(
                    "增加" + "、".join(_related_field_label(f, chn=chn) for f in incl)
                    if chn
                    else "add " + ", ".join(_related_field_label(f, chn=False) for f in incl)
                )
            if notes:
                note_txt = "；".join(notes) if chn else "; ".join(notes)
                parts.append(
                    f"將匯出「{export_kw}」的相關資料至 Excel（{note_txt}）。"
                    if chn
                    else f"Exporting related data for {export_kw} to Excel ({note_txt})."
                )
            else:
                parts.append(
                    f"將匯出「{export_kw}」的相關資料至 Excel。"
                    if chn
                    else f"Exporting related data for {export_kw} to Excel."
                )
    if sources and llm_reply and not (
        related_data is not None and _looks_like_related_search_request(msg)
    ):
        parts.append("參考文件：" + "、".join(s["name"] for s in sources[:3]))
    if _looks_like_analysis_request(msg):
        parts.append(_summarize_needs(msg, history, sources, rel_summary, lang))

    return {
        "reply": "\n".join(p for p in parts if p).strip(),
        "actions": actions,
        "sources": sources,
        "llm_enabled": _llm_enabled_for(base_dir, user_no),
    }
