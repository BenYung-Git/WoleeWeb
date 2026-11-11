from __future__ import annotations

import os
import sqlite3

from core.access_pool import get_access_backend
from typing import Optional, Tuple

from core.db_backend import DbBackendBase, SQLiteBackend


def _is_sqlite_path(db_path: str) -> bool:
    ext = os.path.splitext((db_path or "").strip().lower())[1]
    return ext in (".sqlite", ".db", ".db3")


def _is_sqlite_writable(db_path: str) -> bool:
    """檔案與所在目錄可寫，且可實際寫入 SQLite（含 journal）。"""
    path = os.path.abspath(db_path or "")
    if not path or not os.path.isfile(path):
        return False
    parent = os.path.dirname(path) or "."
    if not os.access(path, os.W_OK) or not os.access(parent, os.W_OK):
        return False
    try:
        conn = sqlite3.connect(path, timeout=2)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS _wolee_write_probe(x INTEGER)")
            conn.execute("INSERT INTO _wolee_write_probe(x) VALUES (1)")
            conn.execute("DELETE FROM _wolee_write_probe")
            conn.execute("DROP TABLE IF EXISTS _wolee_write_probe")
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def is_likely_network_db_path(db_path: str) -> bool:
    """UNC／對應網路磁碟機（如 Samba 的 S:）上的檔案。"""
    path = os.path.abspath(db_path or "")
    if not path:
        return False
    norm = path.replace("/", "\\")
    if norm.startswith("\\\\"):
        return True
    try:
        import ctypes

        root = os.path.splitdrive(path)[0]
        if root:
            dtype = int(ctypes.windll.kernel32.GetDriveTypeW(root + "\\"))
            # DRIVE_REMOTE = 4
            if dtype == 4:
                return True
    except Exception:
        pass
    return False


def prepare_sqlite_for_write(db_path: str) -> Optional[str]:
    """
    寫入前準備：戳破快取、WAL checkpoint，網路碟改 DELETE journal。
    失敗回傳錯誤訊息；成功回傳 None。
    若僅 journal 切換因鎖定失敗，但探測寫入仍成功，則視為可繼續。
    """
    path = os.path.abspath(db_path or "")
    if not path or not os.path.isfile(path):
        return f"找不到資料庫：{path or '(empty)'}"
    bust_sqlite_os_cache(path)
    parent = os.path.dirname(path) or "."
    if not os.access(path, os.W_OK) or not os.access(parent, os.W_OK):
        return (
            f"資料庫不可寫入：{path}。"
            f"請確認檔案與目錄「{parent}」可寫，且非唯讀掛載；"
            f"並關閉其他正在開啟此庫的程式後重試。"
        )
    try:
        conn = sqlite3.connect(path, timeout=60)
        try:
            conn.execute("PRAGMA busy_timeout=60000")
            if is_likely_network_db_path(path):
                # SMB／Samba 上 WAL 鎖不可靠，易出現 readonly／malformed
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                try:
                    conn.execute("PRAGMA journal_mode=DELETE")
                except Exception:
                    pass
            else:
                try:
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except Exception:
                    pass
            # 實際寫入探測（短交易）
            conn.execute("CREATE TABLE IF NOT EXISTS _wolee_write_probe(x INTEGER)")
            conn.execute("INSERT INTO _wolee_write_probe(x) VALUES (1)")
            conn.execute("DELETE FROM _wolee_write_probe")
            conn.execute("DROP TABLE IF EXISTS _wolee_write_probe")
            conn.commit()
        finally:
            conn.close()
        return None
    except Exception as ex:
        # 他程式佔用時 journal 切換可能失敗；若仍可寫則放行
        if _is_sqlite_writable(path):
            return None
        msg = str(ex)
        hint = ""
        low = msg.lower()
        if "locked" in low or "readonly" in low or "read-only" in low:
            hint = " 請關閉其他正在開啟此公司庫的程式（桌面／Web／DB 工具）後再試。"
        return f"無法準備寫入資料庫：{msg}。{hint}".strip()


def resolve_metadata_db_path(base_dir: str, work_db: str) -> Optional[str]:
    """
    將 PROGRAM.WORK_DB（如 USER_DATA.MDB、SYS_DATA.MDB）解析為實際檔案路徑。
    """
    from core.auth import resolve_sys_data_path, resolve_user_data_path

    w = (work_db or "").strip()
    if not w:
        return None
    upper = w.replace("\\", "/").upper()
    if "USER_DATA" in upper:
        return resolve_user_data_path(base_dir)
    if "SYS_DATA" in upper:
        return resolve_sys_data_path(base_dir)
    return None


def sanitize_company_db_key(co_key: str) -> str:
    """
    公司資料庫鍵須為單一代碼（如 GS）。
    含 / 或 \\ 的值為多公司清單，須用 parse_company_list 解析。
    """
    key = (co_key or "").strip()
    if not key:
        return ""
    if "/" in key or "\\" in key:
        return ""
    if key.upper().endswith((".MDB", ".SQLITE", ".DB", ".DB3")):
        return ""
    return key


def parse_company_list(value: str) -> list[str]:
    """解析 PRG_CO 多公司清單，如 GS/LCK/WLS。"""
    raw = (value or "").replace("\\", "/")
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(";", ",").replace("|", ",").split("/"):
        for token in part.split(","):
            k = sanitize_company_db_key(token)
            if not k:
                continue
            ku = k.upper()
            if ku in seen:
                continue
            seen.add(ku)
            out.append(ku)
    return out


def resolve_program_company_key(
    program_prg_co: str, session_company_key: str
) -> tuple[str, Optional[str]]:
    """
    依 PROGRAM.PRG_CO 與登入公司決定營運資料庫鍵：
    - PRG_CO 空白：登入公司
    - PRG_CO = WLS：僅 WLS 登入可開啟，使用 WLS.sqlite
    - PRG_CO = GS/LCK/WLS：登入公司須在清單內，使用登入公司資料庫

    回傳 (company_key, error_message)；error_message 非空表示登入公司不適用。
    """
    session = sanitize_company_db_key(session_company_key) or "GS"
    raw = (program_prg_co or "").strip()
    if not raw:
        return session, None

    single = sanitize_company_db_key(raw)
    if single:
        if session.upper() != single.upper():
            return "", "找不到公司"
        return session, None

    allowed = parse_company_list(raw)
    if not allowed:
        return session, None
    if session.upper() in allowed:
        return session, None
    return "", "找不到公司"


def resolve_company_db_path(base_dir: str, co_key: str) -> str:
    """
    依公司鍵解析營運資料庫路徑（優先 .sqlite，其次 .MDB）。
    Linux／Samba 檔名大小寫可能與鍵值不一致（如 Transfer.sqlite），
    故在精確比對失敗後改以不區分大小寫搜尋目錄。
    """
    key = sanitize_company_db_key(co_key) or "GS"
    base = os.path.abspath(base_dir)
    exts = (".sqlite", ".db", ".db3", ".MDB", ".mdb")
    for ext in exts:
        p = os.path.join(base, f"{key}{ext}")
        if os.path.isfile(p):
            return p
    found = _find_db_file_ci(base, key, exts)
    if found:
        return found
    return os.path.join(base, f"{key}.sqlite")


def _find_db_file_ci(
    base_dir: str, stem: str, extensions: tuple[str, ...]
) -> Optional[str]:
    """在目錄中以不區分大小寫方式尋找 stem+extension 檔案。"""
    try:
        names = os.listdir(base_dir)
    except OSError:
        return None
    by_upper = {n.upper(): n for n in names if n}
    stem_u = (stem or "").upper()
    for ext in extensions:
        hit = by_upper.get(f"{stem_u}{ext.upper()}")
        if not hit:
            continue
        full = os.path.join(base_dir, hit)
        if os.path.isfile(full):
            return full
    return None


_KNOWN_NON_COMPANY_DB_STEMS = frozenset(
    {"SYS_DATA", "USER_DATA", "TRANSFER", "_WOLEE_WRITE_PROBE"}
)


def company_db_exists(base_dir: str, co_key: str) -> bool:
    """公司鍵在同目錄下是否有對應 .sqlite / .MDB 檔。"""
    path = resolve_company_db_path(base_dir, co_key)
    return os.path.isfile(path)


def format_company_db_missing_error(base_dir: str, co_key: str) -> str:
    """登入公司無對應資料庫檔時的說明訊息。"""
    key = sanitize_company_db_key(co_key) or (co_key or "").strip() or "?"
    expected = f"{key}.sqlite 或 {key}.mdb"
    return f"沒有公司資料庫：{key}（請在程式目錄放置 {expected}）"


def filter_companies_with_db(
    base_dir: str, keys: list[str]
) -> tuple[list[str], list[str]]:
    """將 sys_co 公司鍵分為「有資料庫檔」與「缺少檔案」兩組（保留原順序）。"""
    available: list[str] = []
    missing: list[str] = []
    for k in keys:
        if company_db_exists(base_dir, k):
            available.append(k)
        else:
            missing.append(k)
    return available, missing


def discover_company_db_keys(base_dir: str) -> list[str]:
    """
    掃描程式目錄內營運資料庫檔名（排除 sys_data、user_data、transfer 等）。
    sys_co 與實際檔案不一致時作為後援清單。
    """
    base = os.path.abspath(base_dir)
    try:
        names = os.listdir(base)
    except OSError:
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() not in (".sqlite", ".db", ".db3", ".mdb"):
            continue
        su = (stem or "").strip().upper()
        if not su or su in _KNOWN_NON_COMPANY_DB_STEMS:
            continue
        if su in seen:
            continue
        seen.add(su)
        keys.append(stem.strip())
    return sorted(keys, key=lambda x: x.upper())


def validate_company_db(base_dir: str, co_key: str) -> Optional[str]:
    """登入公司無對應資料庫檔時回傳錯誤訊息。"""
    if company_db_exists(base_dir, co_key):
        return None
    return format_company_db_missing_error(base_dir, co_key)


def ensure_company_db_path(base_dir: str, co_key: str) -> tuple[str, Optional[str]]:
    """解析公司資料庫路徑；不存在時回傳 (預期路徑, 錯誤訊息)。"""
    path = resolve_company_db_path(base_dir, co_key)
    if os.path.isfile(path):
        return path, None
    return path, format_company_db_missing_error(base_dir, co_key)


def _looks_like_windows_abs_path(path: str) -> bool:
    p = (path or "").replace("/", "\\").strip()
    return len(p) >= 3 and p[1] == ":" and p[0].isalpha() and p[2] in ("\\", "/")


def align_windows_folder_to_base(win_folder: str, base_dir: str) -> Optional[str]:
    """
    將瀏覽器送來的 Windows 路徑（如 S:\\Share\\WoleeWeb）對齊到 Web 伺服器 base_dir。
    以路徑尾段比對（Share/WoleeWeb），成功則回傳對應的本機／掛載路徑。
    """
    rest = (win_folder or "").replace("\\", "/").strip()
    if len(rest) >= 2 and rest[1] == ":" and rest[0].isalpha():
        rest = rest[2:]
    rest_parts = [p for p in rest.split("/") if p]
    if not rest_parts:
        return None
    base_abs = os.path.abspath(base_dir or ".")
    base_parts = [p for p in base_abs.replace("\\", "/").split("/") if p]
    if not base_parts:
        return None
    rest_l = [p.lower() for p in rest_parts]
    base_l = [p.lower() for p in base_parts]
    for n in range(len(base_l), 0, -1):
        suffix = base_l[-n:]
        for i in range(0, len(rest_l) - n + 1):
            if rest_l[i : i + n] != suffix:
                continue
            extra = rest_parts[i + n :]
            return os.path.abspath(os.path.join(base_abs, *extra)) if extra else base_abs
    return None


def _transfer_sqlite_in_folder(folder: str) -> Optional[str]:
    """若資料夾內有 TRANSFER.sqlite（大小寫不拘），回傳完整路徑。"""
    base = (folder or "").strip()
    if not base or not os.path.isdir(base):
        return None
    exts = (".sqlite", ".db", ".db3")
    for ext in exts:
        p = os.path.join(base, f"TRANSFER{ext}")
        if os.path.isfile(p):
            return p
    return _find_db_file_ci(base, "TRANSFER", exts)


# 規格預設來源：S:\Share\docBiz\Transfer\Transfer.sqlite
SPEC_TRANSFER_FOLDER = r"S:\Share\docBiz\Transfer"


def resolve_spec_transfer_folder(base_dir: str = "") -> Optional[str]:
    """
    若規格預設路徑存在 TRANSFER.sqlite，回傳該資料夾；否則 None。
    重新執行 DO_DATAIMPORT 時應優先使用此路徑。
    """
    from core.attachment_path_map import apply_attachment_path_mappings

    base_abs = os.path.abspath(base_dir or ".") if base_dir else ""
    for raw in (SPEC_TRANSFER_FOLDER, r"S:/Share/docBiz/Transfer"):
        mapped = raw
        if base_abs:
            try:
                mapped = apply_attachment_path_mappings(raw, base_abs) or raw
            except Exception:
                mapped = raw
        try:
            folder = os.path.abspath(mapped)
        except (OSError, ValueError):
            continue
        if _transfer_sqlite_in_folder(folder):
            return folder
    return None


def _folder_looks_like_biz_transfer(folder: str) -> bool:
    """業務來源常見為 …/docBiz/Transfer（非應用程式目錄內副本）。"""
    parts = [p.lower() for p in folder.replace("\\", "/").split("/") if p]
    if len(parts) < 2:
        return False
    return parts[-1] == "transfer" and parts[-2] == "docbiz"


def _count_unposted_in_transfer(db_path: str) -> int:
    """粗估未過帳主檔筆數（PUR_HEADER／INV_HEADER 的 POSTED=FALSE）。失敗回 -1。"""
    path = os.path.abspath(db_path or "")
    if not path or not os.path.isfile(path):
        return -1
    try:
        bust_sqlite_os_cache(path)
    except Exception:
        pass
    conn = None
    try:
        uri = path.replace("\\", "/")
        if len(uri) >= 2 and uri[1] == ":":
            uri = "/" + uri
        conn = sqlite3.connect(f"file:{uri}?mode=ro&cache=private", uri=True, timeout=10)
        total = 0
        tables = {
            str(r[0]).upper(): str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for logical in ("PUR_HEADER", "INV_HEADER"):
            real = tables.get(logical)
            if not real:
                continue
            cols = [
                str(r[1]).upper()
                for r in conn.execute(f'PRAGMA table_info("{real}")').fetchall()
            ]
            if "POSTED" not in cols:
                continue
            # 0 / FALSE / 'FALSE' / '' 視為未過帳
            n = conn.execute(
                f'SELECT COUNT(*) FROM "{real}" WHERE '
                f"POSTED IS NULL OR TRIM(CAST(POSTED AS TEXT)) IN ('', '0', 'FALSE', 'False', 'false')"
            ).fetchone()
            total += int(n[0] or 0) if n else 0
        return total
    except Exception:
        return -1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def resolve_default_transfer_folder(base_dir: str) -> Tuple[str, Optional[str]]:
    """
    決定 DATAIMPORT 預設來源資料夾。
    優先序：
      1. 環境變數 WOLEE_TRANSFER_DIR
      2. 規格預設 S:\\Share\\docBiz\\Transfer\\Transfer.sqlite（若存在）
      3. 其他業務路徑 …/docBiz/Transfer
      4. 未過帳筆數較多者，其次檔案 mtime 較新者
      5. 應用目錄 base_dir
    回傳 (folder, note)。
    """
    from core.attachment_path_map import (
        apply_attachment_path_mappings,
        load_attachment_path_mappings,
    )

    base_abs = os.path.abspath(base_dir or ".")
    parent = os.path.dirname(base_abs)
    candidates: list[str] = []

    env = (os.environ.get("WOLEE_TRANSFER_DIR") or "").strip()
    if env:
        candidates.append(env)

    # 規格明確預設：S:\Share\docBiz\Transfer\Transfer.sqlite
    preferred = resolve_spec_transfer_folder(base_abs)
    if preferred and not env:
        db = _transfer_sqlite_in_folder(preferred)
        if db:
            return preferred, f"預設來源：{db}"

    preferred_folders = (
        SPEC_TRANSFER_FOLDER,
        r"S:/Share/docBiz/Transfer",
    )
    for pref in preferred_folders:
        mapped = apply_attachment_path_mappings(pref, base_abs) or pref
        candidates.append(mapped)

    for rel in (
        os.path.join(parent, "docBiz", "Transfer"),
        os.path.join(parent, "DocBiz", "Transfer"),
        os.path.join(base_abs, "..", "docBiz", "Transfer"),
        os.path.join(base_abs, "docBiz", "Transfer"),
    ):
        candidates.append(rel)

    for _src, dst in load_attachment_path_mappings(base_abs):
        d = (dst or "").strip()
        if not d:
            continue
        candidates.append(os.path.join(d, "Transfer"))
        candidates.append(os.path.join(d, "docBiz", "Transfer"))

    for win in (
        r"S:\Share\docBiz\Transfer",
        r"S:\docBiz\Transfer",
        r"Q:\docBiz\Transfer",
    ):
        mapped = apply_attachment_path_mappings(win, base_abs)
        if mapped:
            candidates.append(mapped)
        candidates.append(win)

    candidates.append(base_abs)

    scored: list[tuple[int, int, float, str, str]] = []
    # (is_env, is_biz, mtime, folder, db_path) — 稍後再依未過帳數重排
    seen: set[str] = set()
    env_abs = ""
    if env:
        try:
            env_abs = os.path.abspath(apply_attachment_path_mappings(env, base_abs) or env)
        except (OSError, ValueError):
            env_abs = ""

    for raw in candidates:
        c = (raw or "").strip()
        if not c:
            continue
        mapped = apply_attachment_path_mappings(c, base_abs)
        for trial in (mapped, c):
            try:
                folder = os.path.abspath(trial)
            except (OSError, ValueError):
                continue
            key = folder.replace("\\", "/").lower()
            if key in seen:
                continue
            seen.add(key)
            if not os.path.isdir(folder):
                continue
            db = _transfer_sqlite_in_folder(folder)
            if not db:
                continue
            try:
                mtime = float(os.path.getmtime(db))
            except OSError:
                mtime = 0.0
            is_env = 1 if env_abs and folder.replace("\\", "/").lower() == env_abs.replace("\\", "/").lower() else 0
            is_biz = 1 if _folder_looks_like_biz_transfer(folder) else 0
            scored.append((is_env, is_biz, mtime, folder, db))

    if not scored:
        return base_abs, None

    # 環境變數指定則直接採用
    for is_env, _is_biz, _mtime, folder, db in scored:
        if is_env:
            return folder, f"使用 WOLEE_TRANSFER_DIR：{db}"

    # 業務 Transfer 目錄優先；同組再比未過帳筆數、mtime
    best = None  # (pending, mtime, is_biz, folder, db)
    for _is_env, is_biz, mtime, folder, db in scored:
        pending = _count_unposted_in_transfer(db)
        # pending=-1 視為 0 以便比較，但略降優先
        pend_score = pending if pending >= 0 else -1
        cand = (is_biz, pend_score, mtime, folder, db)
        if best is None:
            best = cand
            continue
        # 先比 is_biz，再比 pending，再比 mtime
        if cand[0] > best[0] or (
            cand[0] == best[0]
            and (
                cand[1] > best[1]
                or (cand[1] == best[1] and cand[2] > best[2])
            )
        ):
            best = cand

    assert best is not None
    _is_biz, pend_score, _mtime, folder, db = best
    note = None
    if folder != base_abs:
        note = (
            f"預設來源：{db}"
            + (f"（未過帳約 {pend_score} 筆）" if pend_score >= 0 else "")
        )
    return folder, note


def normalize_transfer_folder(
    base_dir: str, folder: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    """
    正規化 DATAIMPORT 來源資料夾。
    回傳 (search_base, warning)。folder 空白則自動選最新／業務預設 TRANSFER 目錄。
    """
    from core.attachment_path_map import apply_attachment_path_mappings

    raw = (folder or "").strip()
    base_abs = os.path.abspath(base_dir or ".")
    if not raw:
        return resolve_default_transfer_folder(base_abs)

    mapped = apply_attachment_path_mappings(raw, base_abs)
    candidates: list[str] = []
    for c in (mapped, raw):
        c = (c or "").strip()
        if c and c not in candidates:
            candidates.append(c)

    for c in candidates:
        try:
            abs_c = os.path.abspath(c)
        except (OSError, ValueError):
            continue
        if os.path.isdir(abs_c):
            warn = None
            if abs_c.replace("\\", "/").lower() != raw.replace("\\", "/").lower():
                warn = f"來源路徑已對應：{raw} → {abs_c}"
            return abs_c, warn

    if _looks_like_windows_abs_path(raw):
        aligned = align_windows_folder_to_base(raw, base_abs)
        if aligned and os.path.isdir(aligned):
            return aligned, f"來源路徑已對應：{raw} → {aligned}"
        # 無法存取時改走預設 TRANSFER 目錄（常為 docBiz/Transfer），勿默默用舊的應用目錄庫
        default_folder, default_note = resolve_default_transfer_folder(base_abs)
        warn = (
            f"來源資料夾「{raw}」在 Web 伺服器無法直接存取，已改用「{default_folder}」。"
            f"若 TRANSFER 在其他掛載點，請設定 attachment_path_map.json 或 WOLEE_TRANSFER_DIR。"
        )
        if default_note:
            warn = f"{warn}\n{default_note}"
        return default_folder, warn

    # 非 Windows 路徑但不存在：仍回傳原解析結果，由後續檢查報錯
    try:
        return os.path.abspath(mapped or raw), None
    except (OSError, ValueError):
        return base_abs, f"無效來源資料夾：{raw}"


def bust_sqlite_os_cache(db_path: str, *, max_bytes: int = 8 * 1024 * 1024) -> None:
    """
    強制重新讀取磁碟／Samba 上的 SQLite 檔內容，降低讀到舊頁面快取的機率。
    小檔（預設 ≤8MB，TRANSFER 適用）會整檔讀過；大檔只讀頭尾。
    """
    path = os.path.abspath(db_path or "")
    if not path or not os.path.isfile(path):
        return
    try:
        st = os.stat(path)
    except OSError:
        return
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        size = int(getattr(st, "st_size", 0) or 0)
        if size <= max_bytes:
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
        else:
            os.read(fd, 256 * 1024)
            if size > 256 * 1024:
                try:
                    os.lseek(fd, max(0, size - 256 * 1024), os.SEEK_SET)
                    os.read(fd, 256 * 1024)
                except OSError:
                    pass
        if hasattr(os, "posix_fadvise") and hasattr(os, "POSIX_FADV_DONTNEED"):
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            except OSError:
                pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        os.stat(path)
    except OSError:
        pass


def snapshot_sqlite_for_fresh_read(db_path: str) -> Tuple[str, Optional[str]]:
    """
    將 SQLite 複製到本機暫存檔後再讀，避免 Samba／NFS 頁面快取造成清單過期。
    回傳 (path_to_open, cleanup_path_or_None)。
    失敗時回退為原路徑（cleanup=None）。
    """
    import shutil
    import tempfile

    src = os.path.abspath(db_path or "")
    if not src or not os.path.isfile(src):
        return src, None
    bust_sqlite_os_cache(src)
    fd, snap = tempfile.mkstemp(prefix="wolee_transfer_", suffix=".sqlite")
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        shutil.copyfile(src, snap)
    except OSError:
        try:
            os.remove(snap)
        except OSError:
            pass
        return src, None
    return snap, snap


def resolve_transfer_db_path(base_dir: str, folder: Optional[str] = None) -> str:
    """
    解析 TRANSFER 暫存資料庫路徑。
    DATAIMPORT 來源表（PUR_HEADER／INV_HEADER／STK 等）皆在此庫。

    folder 有值時：在該資料夾尋找 TRANSFER.sqlite；
    否則在 base_dir 尋找。
    """
    key = "TRANSFER"
    base, _warn = normalize_transfer_folder(base_dir, folder)
    exts = (".sqlite", ".db", ".db3")
    for ext in exts:
        p = os.path.join(base, f"{key}{ext}")
        if os.path.isfile(p):
            return p
    found = _find_db_file_ci(base, key, exts)
    if found:
        return found
    return os.path.join(base, f"{key}.sqlite")


def ensure_transfer_db_path(base_dir: str) -> tuple[str, Optional[str]]:
    """
    解析 TRANSFER 資料庫路徑（直接使用共用目錄 TRANSFER.sqlite，不建本機副本）。
    僅確認檔案可讀（供開啟對話框／列清單）；寫入權限於執行匯入時再檢查。
    回傳 (path, error)。
    """
    prepared = prepare_transfer_db_for_import(base_dir, for_write=False)
    return prepared[0], prepared[2]


def prepare_transfer_db_for_import(
    base_dir: str,
    *,
    for_write: bool = False,
    folder: Optional[str] = None,
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    準備 DATAIMPORT 用的 TRANSFER 連線路徑。
    直接使用指定資料夾（或 base_dir）的 TRANSFER.sqlite。

    folder：使用者選擇的來源資料夾（可依 PURCHASE／INVOICE／STOCK 不同）。
    for_write=False：僅讀取待匯入清單，不檢查寫入權限。
    for_write=True：執行匯入前檢查可寫（需更新 POSTED）。

    回傳 (path, share_path_or_None, error, warning)。
    """
    search_base, folder_warn = normalize_transfer_folder(base_dir, folder)
    path = resolve_transfer_db_path(base_dir, folder=search_base)
    if not os.path.isfile(path):
        hint_names: list[str] = []
        try:
            for n in sorted(os.listdir(search_base)):
                if n.upper().startswith("TRANSFER"):
                    hint_names.append(n)
        except OSError:
            pass
        if hint_names:
            return (
                path,
                None,
                (
                    f"找不到 TRANSFER.sqlite（已解析：{path}）。"
                    f"目錄中有：{', '.join(hint_names)}。"
                    f"DATAIMPORT 僅使用 TRANSFER.sqlite，請確認檔案存在。"
                ),
                folder_warn,
            )
        return (
            path,
            None,
            (
                f"找不到 TRANSFER 資料庫：{path}。"
                f"請在 {search_base} 放置 TRANSFER.sqlite。"
            ),
            folder_warn,
        )

    if not _is_sqlite_path(path):
        return (
            path,
            None,
            (
                f"DATAIMPORT 僅使用 TRANSFER.sqlite，目前解析到非 SQLite 檔：{path}。"
            ),
            folder_warn,
        )

    # 讀／寫前都先戳一下 OS／Samba 快取
    bust_sqlite_os_cache(path)

    warn = folder_warn
    if for_write and not _is_sqlite_writable(path):
        parent = os.path.dirname(path) or "."
        return (
            path,
            None,
            (
                f"TRANSFER 資料庫不可寫入：{path}。"
                f"DATAIMPORT 需更新 POSTED，請開放檔案與目錄寫入權限"
                f"（例：chmod u+w 「{path}」與「{parent}」），"
                f"並確認 Samba／掛載非唯讀。"
            ),
            warn,
        )

    return path, None, None, warn


def sync_transfer_db_to_share(
    writable_path: str, share_path: Optional[str]
) -> Optional[str]:
    """保留相容：已不再使用本機副本，恒回傳 None。"""
    return None


def get_backend_for_path(db_path: str) -> DbBackendBase:
    """
    依副檔名回傳資料庫後端：
    - .sqlite/.db/.db3 -> SQLiteBackend
    - 其他 -> AccessBackend（共用 access_pool）
    """
    path = os.path.abspath(db_path)
    if _is_sqlite_path(path):
        return SQLiteBackend(path)
    return get_access_backend(path)
