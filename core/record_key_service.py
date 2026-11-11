"""主檔儲存前依 PROGRAM.KEY_CODE / NUM_TYPE / NUM_CONTROL / NUM_DIGIT / NUM_SEPARATE 產生單據鍵。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from core.db_backend import DbBackendBase
from core.menu_loader import ProgramItem


class ManualKeyRequired(Exception):
    """NUM_CONTROL 與 NUM_TYPE 皆未設定：需使用者於新增編號介面指定 KEY。"""

    def __init__(self, *, key_field: str, suggested_key: str, message: str = "") -> None:
        super().__init__(message or "manual key required")
        self.key_field = key_field
        self.suggested_key = suggested_key


@dataclass(frozen=True)
class ProgramNumberConfig:
    """PROGRAM 上單據編號規則（欄位名為工作表實體欄名）。"""

    key_field: str
    num_type_field: str = ""
    num_control_field: str = ""
    num_digit: int = 8
    num_separate: str = ""

    @property
    def auto_numbering(self) -> bool:
        """NUM_CONTROL 或 NUM_TYPE 任一不空白 → 自動編號。"""
        return bool(
            (self.num_control_field or "").strip() or (self.num_type_field or "").strip()
        )


def config_from_program(prg: Optional[ProgramItem]) -> Optional[ProgramNumberConfig]:
    if prg is None:
        return None
    key_field = (prg.key_code or "").strip()
    if not key_field:
        return None
    num_type = (prg.num_type or "").strip()
    num_control = (prg.num_control or "").strip()
    digits = int(prg.num_digit or 0)
    if digits <= 0:
        digits = 8
    # NUM_SEPARATE 可為 "-"；None 視為空白（無分隔）
    separate = "" if prg.num_separate is None else str(prg.num_separate)
    return ProgramNumberConfig(
        key_field=key_field,
        num_type_field=num_type,
        num_control_field=num_control,
        num_digit=digits,
        num_separate=separate,
    )


def resolve_program_number_config(
    program_repo, do_proc: str
) -> Optional[ProgramNumberConfig]:
    """自 PROGRAM（含 WORK_PROC 解析）取得編號規則。"""
    binding = program_repo.resolve_program_binding(do_proc)
    candidates = [
        program_repo.find_by_do_proc((binding.rule_proc or "").strip()),
        binding.data_item,
        binding.menu_item,
        program_repo.find_by_do_proc(do_proc),
    ]
    for prg in candidates:
        cfg = config_from_program(prg)
        if cfg is not None:
            return cfg
    return None


def resolve_field_name(field_names: Sequence[str], name: str) -> Optional[str]:
    target = (name or "").strip().upper()
    if not target:
        return None
    for f in field_names:
        if str(f or "").strip().upper() == target:
            return str(f)
    return None


def _field_index(field_names: Sequence[str], name: str) -> Optional[int]:
    resolved = resolve_field_name(field_names, name)
    if not resolved:
        return None
    for i, f in enumerate(field_names):
        if f == resolved:
            return i
    return None


def _form_value(form_values: Dict[str, str], field_name: Optional[str]) -> str:
    if not field_name:
        return ""
    direct = form_values.get(field_name)
    if direct is not None and str(direct).strip():
        return str(direct).strip()
    want = str(field_name).strip().upper()
    for k, v in (form_values or {}).items():
        if str(k).strip().upper() == want:
            return str(v or "").strip()
    return ""


def compose_document_key(type_val: str, padded_no: str, separate: str) -> str:
    """
    KEY = NUM_TYPE值 + NUM_SEPARATE + NUM_CONTROL（補零）。
    例：TX_TYPE=GS, NUM_SEPARATE=-, TX_NO=00000001 → GS-00000001
    """
    tv = (type_val or "").strip()
    pd = (padded_no or "").strip()
    sep = "" if separate is None else str(separate)
    if tv and sep:
        return f"{tv}{sep}{pd}"
    if tv:
        return f"{tv}{pd}"
    return pd


def _parse_trailing_int(text: str) -> Tuple[str, int]:
    s = str(text or "").strip()
    if not s:
        return "", 0
    i = len(s)
    while i > 0 and s[i - 1].isdigit():
        i -= 1
    prefix = s[:i]
    num_part = s[i:]
    if not num_part:
        return s, 0
    try:
        return prefix, int(num_part)
    except ValueError:
        return s, 0


def _pad_number(n: int, digits: int) -> str:
    d = max(1, int(digits or 1))
    if n < 0:
        n = 0
    return str(n).zfill(d)


def _row_val(row: Sequence[str], idx: Optional[int]) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _key_exists(
    backend: DbBackendBase,
    table_name: str,
    physical_fields: Sequence[str],
    key_field: str,
    key_value: str,
    *,
    exclude_row: Optional[Sequence[str]] = None,
) -> bool:
    kv = (key_value or "").strip()
    if not kv:
        return False
    rows = backend.fetch_rows_where(
        table_name, key_field, kv, limit=5, column_order=list(physical_fields)
    )
    if not rows:
        return False
    if exclude_row is None:
        return True
    ex = [str(x or "").strip() for x in exclude_row]
    for r in rows:
        if [str(x or "").strip() for x in r] != ex:
            return True
    return False


def _max_control_for_group(
    rows: Sequence[Sequence[str]],
    *,
    type_idx: Optional[int],
    control_idx: Optional[int],
    group_value: str,
) -> int:
    gv = (group_value or "").strip()
    best = 0
    for row in rows:
        if type_idx is not None:
            if _row_val(row, type_idx) != gv:
                continue
        raw = _row_val(row, control_idx)
        if not raw:
            continue
        try:
            n = int(raw)
        except ValueError:
            _, n = _parse_trailing_int(raw)
        if n > best:
            best = n
    return best


def _max_key_suffix(
    rows: Sequence[Sequence[str]],
    key_idx: Optional[int],
    *,
    prefix: str = "",
    type_idx: Optional[int] = None,
    group_value: str = "",
) -> int:
    """在 KEY_CODE 中取最大流水號；可依 NUM_TYPE 組別與鍵值前置過濾。"""
    pfx = prefix or ""
    gv = (group_value or "").strip()
    best = 0
    for row in rows:
        if type_idx is not None and gv:
            if _row_val(row, type_idx) != gv:
                continue
        key = _row_val(row, key_idx)
        if not key:
            continue
        pre, n = _parse_trailing_int(key)
        if pfx and pre != pfx:
            continue
        if n > best:
            best = n
    return best


def suggest_manual_key(
    backend: DbBackendBase,
    table_name: str,
    physical_fields: Sequence[str],
    cfg: ProgramNumberConfig,
    form_values: Dict[str, str],
) -> str:
    """
    手動編號預設 KEY_CODE：
    - 有組別值：組內最後流水 +1，並套用 NUM_SEPARATE
    - 否則：全表最後編號 +1
    """
    rows = backend.fetch_rows(
        table_name, "", False, limit=50000, column_order=list(physical_fields)
    )
    key_idx = _field_index(physical_fields, cfg.key_field)
    type_idx = (
        _field_index(physical_fields, cfg.num_type_field)
        if cfg.num_type_field
        else None
    )
    type_field = resolve_field_name(physical_fields, cfg.num_type_field)
    type_val = _form_value(form_values, type_field)
    sep = cfg.num_separate or ""

    if type_val:
        key_prefix = f"{type_val}{sep}" if sep else type_val
        next_n = (
            _max_key_suffix(
                rows,
                key_idx,
                prefix=key_prefix,
                type_idx=type_idx,
                group_value=type_val,
            )
            + 1
        )
        if next_n <= 1:
            next_n = (
                _max_key_suffix(
                    rows,
                    key_idx,
                    prefix="",
                    type_idx=type_idx,
                    group_value=type_val,
                )
                + 1
            )
        return compose_document_key(type_val, _pad_number(next_n, cfg.num_digit), sep)

    prefix = ""
    if key_idx is not None and rows:
        for row in rows:
            key = _row_val(row, key_idx)
            if key:
                pre, _ = _parse_trailing_int(key)
                if pre:
                    prefix = pre
                    break
    next_n = _max_key_suffix(rows, key_idx, prefix=prefix) + 1
    padded = _pad_number(next_n, cfg.num_digit)
    if prefix:
        return f"{prefix}{padded}"
    return padded


def allocate_auto_key(
    backend: DbBackendBase,
    table_name: str,
    physical_fields: Sequence[str],
    cfg: ProgramNumberConfig,
    form_values: Dict[str, str],
    *,
    exclude_row: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """
    自動編號：
    - 依 NUM_TYPE 欄位值分組
    - NUM_CONTROL = 該組最後編號 +1（NUM_DIGIT 前置補零文字）
    - KEY_CODE = NUM_TYPE值 + NUM_SEPARATE + NUM_CONTROL
      例：GS + - + 00000001 → GS-00000001
    - 若 KEY 已存在則流水 +1，直到唯一
    """
    if not cfg.auto_numbering:
        raise ValueError("not auto numbering")

    out = dict(form_values)
    type_field = resolve_field_name(physical_fields, cfg.num_type_field)
    ctrl_field = resolve_field_name(physical_fields, cfg.num_control_field)
    key_field = resolve_field_name(physical_fields, cfg.key_field)
    if not key_field:
        raise ValueError("missing key field")
    if cfg.num_control_field and not ctrl_field:
        raise ValueError("missing num control field")

    type_val = _form_value(out, type_field)
    sep = cfg.num_separate or ""
    rows = backend.fetch_rows(
        table_name, "", False, limit=50000, column_order=list(physical_fields)
    )
    type_idx = _field_index(physical_fields, cfg.num_type_field) if type_field else None
    ctrl_idx = (
        _field_index(physical_fields, cfg.num_control_field) if ctrl_field else None
    )
    key_idx = _field_index(physical_fields, cfg.key_field)

    if ctrl_idx is not None:
        next_n = (
            _max_control_for_group(
                rows, type_idx=type_idx, control_idx=ctrl_idx, group_value=type_val
            )
            + 1
        )
    else:
        key_prefix = f"{type_val}{sep}" if type_val else ""
        next_n = (
            _max_key_suffix(
                rows,
                key_idx,
                prefix=key_prefix,
                type_idx=type_idx,
                group_value=type_val,
            )
            + 1
        )

    if next_n < 1:
        next_n = 1

    padded = _pad_number(next_n, cfg.num_digit)
    key_val = compose_document_key(type_val, padded, sep)

    guard = 0
    while _key_exists(
        backend,
        table_name,
        physical_fields,
        key_field,
        key_val,
        exclude_row=exclude_row,
    ):
        next_n += 1
        padded = _pad_number(next_n, cfg.num_digit)
        key_val = compose_document_key(type_val, padded, sep)
        guard += 1
        if guard > 100000:
            raise ValueError("cannot allocate unique key")

    if ctrl_field:
        out[ctrl_field] = padded
    out[key_field] = key_val
    return out


def merge_allocated_key_fields(
    field_names: List[str],
    values: List[str],
    cfg: Optional[ProgramNumberConfig],
    form_values: Dict[str, str],
    physical_fields: Sequence[str],
) -> Tuple[List[str], List[str]]:
    """確保自動編號寫入的 KEY_CODE／NUM_CONTROL 欄位會進入 INSERT 欄位清單。"""
    if cfg is None:
        return field_names, values
    out_fields = list(field_names)
    out_values = [str(v) if v is not None else "" for v in values]
    present = {(f or "").strip().upper(): i for i, f in enumerate(out_fields)}
    for logical in (cfg.key_field, cfg.num_control_field):
        if not (logical or "").strip():
            continue
        name = resolve_field_name(physical_fields, logical)
        if not name:
            continue
        has_key = any(
            str(k).strip().upper() == name.upper() for k in (form_values or {})
        )
        if not has_key:
            continue
        val = _form_value(form_values, name)
        idx = present.get(name.upper())
        if idx is None:
            out_fields.append(name)
            out_values.append(val)
            present[name.upper()] = len(out_fields) - 1
        else:
            out_values[idx] = val
    return out_fields, out_values


def prepare_record_key_values(
    backend: DbBackendBase,
    table_name: str,
    physical_fields: Sequence[str],
    cfg: Optional[ProgramNumberConfig],
    form_values: Dict[str, str],
    *,
    is_new: bool,
    exclude_row: Optional[Sequence[str]] = None,
    manual_key: str = "",
) -> Dict[str, str]:
    """
    新增／複製儲存前準備鍵值。
    - 自動編號（NUM_CONTROL 或 NUM_TYPE 非空白）：直接回傳更新後 form_values
    - 手動編號（兩者皆空白）：未提供 manual_key 時拋 ManualKeyRequired
    """
    if not is_new or cfg is None:
        return dict(form_values)

    key_field = resolve_field_name(physical_fields, cfg.key_field)
    if not key_field:
        return dict(form_values)

    if cfg.auto_numbering:
        return allocate_auto_key(
            backend,
            table_name,
            physical_fields,
            cfg,
            form_values,
            exclude_row=exclude_row,
        )

    mk = (manual_key or "").strip()
    if mk:
        out = dict(form_values)
        out[key_field] = mk
        if _key_exists(
            backend,
            table_name,
            physical_fields,
            key_field,
            mk,
            exclude_row=exclude_row,
        ):
            raise ValueError("duplicate key")
        return out

    current_key = _form_value(form_values, key_field)
    suggested = current_key or suggest_manual_key(
        backend, table_name, physical_fields, cfg, form_values
    )
    raise ManualKeyRequired(key_field=key_field, suggested_key=suggested)
