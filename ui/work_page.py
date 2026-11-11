from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from PyQt6.QtCore import (
    Qt,
    QAbstractTableModel,
    QByteArray,
    QMimeData,
    QModelIndex,
    QEvent,
    QDate,
    QObject,
    QSize,
    QTimer,
    QItemSelectionModel,
)
from PyQt6.QtGui import QFont, QFontMetrics, QGuiApplication

from PyQt6.QtWidgets import (
    QComboBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QLineEdit,
    QLabel,
    QPushButton,
    QSizePolicy,
    QDialog,
    QScrollArea,
    QTextEdit,
    QDateEdit,
    QGridLayout,
    QDialogButtonBox,
    QMessageBox,
    QTabWidget,
    QTableWidget,
    QAbstractItemView,
    QHeaderView,
    QTableWidgetItem,
    QStyle,
    QSplitter,
    QStyledItemDelegate,
    QAbstractItemDelegate,
    QStyleOptionViewItem,
    QMenu,
    QFrame,
)
from core.grid_sort import (
    GridSortKey,
    sort_indicator_text,
    sort_rows_by_stack,
    toggle_grid_sort_stack,
)
from core.data_dictionary import (
    DataDictionary,
    LanguageCode,
    WorkActionFlags,
    merge_work_action_flags,
)
from core.ui_font_settings import (
    get_ui_font_settings,
    load_ui_font_settings,
    set_ui_font_settings,
)
from core.ui_icon_map import icon_from_key
from core.display_format import (
    APP_DATE_QT_FORMAT,
    data_format_looks_like_date,
    format_cell_display,
    guess_number_kind,
    is_boolean_data_type,
    is_date_data_type,
    is_date_field,
    is_numeric_data_type,
    is_string_data_type,
    normalize_storage_value,
    parse_qdate,
)
from core.record_key_service import (
    ManualKeyRequired,
    ProgramNumberConfig,
    merge_allocated_key_fields,
    prepare_record_key_values,
)
from core.row_insert_defaults import (
    apply_insert_bit_defaults,
    arap_field_locked_by_tx_type,
    arap_vou_type_for_tx_type,
    empty_form_values_for_add_from_dict,
    is_do_arap_proc,
)
from core.row_where import delete_tx_rows_for_master, resolve_update_where
from core.tx_row_order import (
    move_row,
    relocate_row,
    renumber_item_no,
)
from core.ui_theme import (
    form_editor_locked_qss,
    form_editor_qss,
    form_label_qss,
    lookup_button_qss,
    nav_button_qss,
    theme_surface_text_color,
    work_action_button_qss,
    work_action_panel_qss,
)
from ui.key_assign_dialog import KeyAssignDialog

if TYPE_CHECKING:
    from core.db_backend import DbBackendBase

# QTableView 主／明細 Grid：表頭／儲存格 pt 見 core.ui_font_settings；欄寬依 WIDTH／內容
_GRID_VISIBLE_ROWS_MAIN = 20
_GRID_ROW_HEIGHT_PX = 26
_GRID_CHAR_MIN = 6
_GRID_CHAR_MAX = 80
_GRID_MAX_SCAN_ROWS = 5000
_GRID_COL_PAD_PX = 28

# 預設輸入介面：標題在左、資料在右；≤20 → 2×10=20；>20 → 3×10=30
# 規劃輸入介面：標題在上、資料在下；≤15 → 3×5=15；>15 → 5×5=25
FORM_LAYOUT_DEFAULT = "default"
FORM_LAYOUT_PLANNED = "planned"
_FORM_ROWS_PER_PAGE = 10
_FORM_LABEL_WIDTH_DEFAULT_PX = 180
_FORM_EDITOR_WIDTH_DEFAULT_PX = 220
_FORM_LABEL_WIDTH_PLANNED_PX = 240
_FORM_EDITOR_WIDTH_PLANNED_PX = 240
_FORM_EDITOR_HEIGHT_PX = 30
# 備註／長文字：佔 2 個欄位槽寬 × 2 列高
_FORM_LONG_TEXT_COL_SPAN = 2
_FORM_LONG_TEXT_ROW_SPAN = 2
_FORM_GRID_V_SPACING_PX = 4
# 查詢對話框等沿用預設輸入介面尺寸
_FORM_LABEL_WIDTH_PX = _FORM_LABEL_WIDTH_DEFAULT_PX
_FORM_LABEL_WIDTH_MIN_PX = _FORM_LABEL_WIDTH_DEFAULT_PX
_FORM_LABEL_WIDTH_MAX_PX = _FORM_LABEL_WIDTH_DEFAULT_PX
_FORM_EDITOR_WIDTH_PX = _FORM_EDITOR_WIDTH_DEFAULT_PX


def _font_base_dir_for(widget: Optional[QWidget]) -> Optional[str]:
    w: Optional[QWidget] = widget
    while w is not None:
        bd = getattr(w, "_app_base_dir", None)
        if bd:
            return str(bd)
        w = w.parent()  # type: ignore[assignment]
    return None


def _grid_cell_pt(base_dir: Optional[str] = None) -> int:
    return get_ui_font_settings(base_dir).grid_cell_pt


def _grid_header_pt(base_dir: Optional[str] = None) -> int:
    return get_ui_font_settings(base_dir).grid_header_pt


def _grid_row_height_px(base_dir: Optional[str] = None) -> int:
    _ = base_dir
    return _GRID_ROW_HEIGHT_PX


def form_label_style(base_dir: Optional[str] = None) -> str:
    pt = get_ui_font_settings(base_dir).form_label_pt
    return form_label_qss(pt)


def form_editor_style(base_dir: Optional[str] = None) -> str:
    pt = get_ui_font_settings(base_dir).form_editor_pt
    return form_editor_qss(pt)


def form_editor_locked_style(base_dir: Optional[str] = None) -> str:
    """ED/AE 鎖定欄：背景與欄位標題一致。"""
    pt = get_ui_font_settings(base_dir).form_editor_pt
    return form_editor_locked_qss(pt)


def _form_field_edit_locked(edit_type: str, *, is_new_record: bool) -> bool:
    et = (edit_type or "").strip().upper()
    if et == "ED":
        return True
    if et == "AE":
        return not is_new_record
    return False


class _LockedFieldMouseFocusFilter(QObject):
    """鎖定欄（EDIT_TYPE=ED）滑鼠點擊時強制取得 FOCUS。"""

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        ):
            if isinstance(obj, QWidget) and obj.isEnabled():
                # 點擊即聚焦（唯讀欄在部分平台不會自動拿焦點）
                if not obj.hasFocus():
                    obj.setFocus(Qt.FocusReason.MouseFocusReason)
                # 若點的是複合控制項外框，改聚焦內部編輯列
                if isinstance(obj, (QDateEdit, QComboBox)):
                    kids = obj.findChildren(QLineEdit)
                    le = kids[0] if kids else None
                    if isinstance(obj, QComboBox) and obj.lineEdit() is not None:
                        le = obj.lineEdit()
                    if le is not None and not le.hasFocus():
                        le.setFocus(Qt.FocusReason.MouseFocusReason)
        return False


_LOCKED_MOUSE_FOCUS_FILTER: Optional[_LockedFieldMouseFocusFilter] = None


def _locked_mouse_focus_filter() -> _LockedFieldMouseFocusFilter:
    global _LOCKED_MOUSE_FOCUS_FILTER
    if _LOCKED_MOUSE_FOCUS_FILTER is None:
        _LOCKED_MOUSE_FOCUS_FILTER = _LockedFieldMouseFocusFilter()
    return _LOCKED_MOUSE_FOCUS_FILTER


def _install_locked_mouse_focus(editor: QWidget) -> None:
    """確保鎖定欄可用滑鼠點擊取得 FOCUS。"""
    flt = _locked_mouse_focus_filter()
    editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    editor.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
    try:
        editor.installEventFilter(flt)
    except Exception:
        pass
    for child in editor.findChildren(QLineEdit):
        child.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        try:
            child.installEventFilter(flt)
        except Exception:
            pass


def apply_form_field_edit_state(
    field: str,
    editor: QWidget,
    display: Optional[QWidget],
    *,
    data_dict: DataDictionary,
    table_name: str,
    is_new_record: bool,
    base_dir: Optional[str],
    force_locked: bool = False,
) -> None:
    """
    依 EDIT_TYPE 設定欄位可否編輯及背景色。
    EDIT_TYPE=ED（及編輯中的 AE）：不可更改，但仍可 FOCUS（含滑鼠點擊）；
    背景色與欄位標題相同。
    force_locked：額外強制鎖定（如 DO_ARAP 依傳票種類鎖收款／付款欄）。
    """
    locked = force_locked or _form_field_edit_locked(
        data_dict.get_edit_type(table_name, field),
        is_new_record=is_new_record,
    )
    style = (
        form_editor_locked_style(base_dir) if locked else form_editor_style(base_dir)
    )
    # 鎖定欄仍可聚焦／Tab／Enter 換欄／滑鼠點擊，僅禁止修改內容
    editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    editor.setProperty("wolee_edit_locked", bool(locked))

    if isinstance(editor, QLineEdit):
        editor.setReadOnly(locked)
        editor.setEnabled(True)
    elif isinstance(editor, QTextEdit):
        editor.setReadOnly(locked)
        editor.setEnabled(True)
    elif isinstance(editor, QDateEdit):
        editor.setReadOnly(locked)
        editor.setEnabled(True)
        # 鎖定時關閉日曆彈窗，避免誤改；仍可聚焦與換欄
        editor.setCalendarPopup(not locked)
    elif isinstance(editor, QComboBox):
        # 不可用 setEnabled(False)：會失去 FOCUS
        editor.setEnabled(True)
        if locked:
            if not editor.isEditable():
                editor.setEditable(True)
            le = editor.lineEdit()
            if le is not None:
                le.setReadOnly(True)
                le.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                le.setStyleSheet(style)
            # 隱藏下拉箭頭，避免開啟清單改值
            editor.setStyleSheet(
                style
                + " QComboBox::drop-down { width: 0px; border: none; }"
                + " QComboBox::down-arrow { image: none; width: 0px; height: 0px; }"
            )
            if not hasattr(editor, "_wolee_orig_show_popup"):
                editor._wolee_orig_show_popup = editor.showPopup  # type: ignore[attr-defined]
            editor.showPopup = lambda: None  # type: ignore[method-assign]
        else:
            le = editor.lineEdit()
            if le is not None and editor.isEditable():
                le.setReadOnly(False)
                le.setStyleSheet(form_editor_style(base_dir))
            editor.setStyleSheet(style)
            orig_popup = getattr(editor, "_wolee_orig_show_popup", None)
            if callable(orig_popup):
                editor.showPopup = orig_popup  # type: ignore[method-assign]
        if locked:
            _install_locked_mouse_focus(editor)
        # Combo 已個別設 style，下面勿再覆寫
        wrap = display if display is not None else editor
        if wrap is not editor:
            for btn in wrap.findChildren(QPushButton):
                btn.setEnabled(not locked)
        return

    editor.setStyleSheet(style)
    # QDateEdit 內部編輯列也要套用標題同色背景，並保持可聚焦
    inner = _form_line_edit_of(editor)
    if inner is not None and inner is not editor:
        if isinstance(editor, QDateEdit):
            inner.setReadOnly(locked)
        inner.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        inner.setStyleSheet(style)

    if locked:
        _install_locked_mouse_focus(editor)

    wrap = display if display is not None else editor
    if wrap is not editor:
        for btn in wrap.findChildren(QPushButton):
            btn.setEnabled(not locked)


def _form_editor_by_name(
    editors: Dict[str, QWidget], field_name: str
) -> Optional[QWidget]:
    want = (field_name or "").strip().upper()
    for f, ed in (editors or {}).items():
        if (f or "").strip().upper() == want and isinstance(ed, QWidget):
            return ed
    return None


def _set_form_editor_plain_text(editor: QWidget, text: str) -> None:
    """寫入欄位文字（不觸發連動）。"""
    if isinstance(editor, QLineEdit):
        if editor.text() == text:
            return
        editor.blockSignals(True)
        editor.setText(text)
        editor.blockSignals(False)
        return
    if isinstance(editor, QComboBox):
        if (editor.currentText() or "") == text:
            return
        editor.blockSignals(True)
        if editor.isEditable():
            editor.setEditText(text)
        else:
            idx = editor.findText(text)
            if idx >= 0:
                editor.setCurrentIndex(idx)
            else:
                editor.setCurrentText(text)
        editor.blockSignals(False)


def _refresh_form_arap_vou_locks(
    *,
    field_meta: List[Dict[str, object]],
    editors: Dict[str, QWidget],
    data_dict: DataDictionary,
    table_name: str,
    is_new_record: bool,
    base_dir: Optional[str],
    proc_name: str = "",
    do_proc: str = "",
) -> None:
    """
    DO_ARAP：依類別設定傳票種類並鎖定欄位。
    AR→RJ 鎖付款欄；AP→PJ 鎖收款欄；ARAP→RPJ 兩邊皆可改。
    """
    if not is_do_arap_proc(proc_name, do_proc):
        return
    tx_ed = _form_editor_by_name(editors, "TX_TYPE")
    tx = _form_editor_text(tx_ed) if tx_ed is not None else ""
    mapped = arap_vou_type_for_tx_type(tx)
    if mapped:
        vou_ed = _form_editor_by_name(editors, "VOU_TYPE")
        if vou_ed is not None:
            _set_form_editor_plain_text(vou_ed, mapped)
    for m in field_meta or []:
        field = str(m.get("field", "") or "")
        editor = m.get("editor")
        display = m.get("display")
        if not field or not isinstance(editor, QWidget):
            continue
        force = arap_field_locked_by_tx_type(
            field, tx, proc_name=proc_name, do_proc=do_proc
        )
        apply_form_field_edit_state(
            field,
            editor,
            display if isinstance(display, QWidget) else None,
            data_dict=data_dict,
            table_name=table_name,
            is_new_record=is_new_record,
            base_dir=base_dir,
            force_locked=force,
        )


def _install_arap_vou_type_lock_hooks(
    editors: Dict[str, QWidget],
    *,
    proc_name: str = "",
    do_proc: str = "",
    on_change: Optional[Callable[[], None]] = None,
) -> None:
    """類別（TX_TYPE）變更時重設傳票種類並重套收款／付款欄鎖定。"""
    if not on_change or not is_do_arap_proc(proc_name, do_proc):
        return
    ed = _form_editor_by_name(editors, "TX_TYPE")
    if ed is None:
        on_change()
        return
    if not getattr(ed, "_wolee_arap_tx_hooked", False):
        ed._wolee_arap_tx_hooked = True  # type: ignore[attr-defined]

        def _fire(_checked: object = None) -> None:
            on_change()

        if isinstance(ed, QLineEdit):
            ed.textChanged.connect(_fire)
            ed.editingFinished.connect(_fire)
        elif isinstance(ed, QComboBox):
            ed.currentTextChanged.connect(lambda _t="": on_change())
            le = ed.lineEdit()
            if le is not None:
                le.textChanged.connect(_fire)
                le.editingFinished.connect(_fire)
    on_change()


def _grid_cell_font(base_dir: Optional[str] = None) -> QFont:
    f = QFont()
    f.setPointSize(_grid_cell_pt(base_dir))
    f.setWeight(QFont.Weight.Normal)
    return f


class GridCellDelegate(QStyledItemDelegate):
    """Grid 儲存格顯示與就地編輯；Enter／方向鍵於儲存格間移動。"""

    def __init__(
        self,
        view: Optional[QAbstractItemView] = None,
        base_dir: Optional[str] = None,
    ) -> None:
        super().__init__(view)
        self._view = view
        self._base_dir = base_dir

    def set_view(self, view: QAbstractItemView) -> None:
        self._view = view

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        option.font = _grid_cell_font(self._base_dir)

    def createEditor(self, parent, option, index):  # type: ignore[override]
        editor = super().createEditor(parent, option, index)
        if editor is not None:
            editor.setFont(_grid_cell_font(self._base_dir))
            editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index) -> None:  # type: ignore[override]
        if editor is not None:
            editor.setFont(_grid_cell_font(self._base_dir))
        super().setEditorData(editor, index)

    def _editor_belongs_to_view(self, editor: QWidget) -> bool:
        view = self._view
        if view is None or editor is None:
            return False
        if view.state() != QAbstractItemView.State.EditingState:
            return False
        vp = view.viewport()
        w: Optional[QWidget] = editor
        while w is not None:
            if w is vp:
                return True
            w = w.parentWidget()
        return False

    def _finish_edit(self, editor: QWidget) -> None:
        if not self._editor_belongs_to_view(editor):
            return
        self.closeEditor.emit(
            editor, QAbstractItemDelegate.EndEditHint.SubmitModelCache
        )

    def _next_editable_cell(
        self, model, row: int, col: int, nrows: int, ncols: int
    ) -> Optional[tuple[int, int]]:
        next_row, next_col = row, col + 1
        while next_row < nrows:
            while next_col < ncols:
                idx = model.index(next_row, next_col)
                if idx.flags() & Qt.ItemFlag.ItemIsEditable:
                    return next_row, next_col
                next_col += 1
            next_col = 0
            next_row += 1
        return None

    def _navigate_from_editor(self, editor: QWidget, row: int, col: int) -> bool:
        view = self._view
        if view is None:
            return False
        model = view.model()
        if model is None:
            return False
        nrows = _grid_data_row_count(view)
        ncols = model.columnCount()
        if not (0 <= row < nrows and 0 <= col < ncols):
            return False

        target = model.index(row, col)
        if not target.isValid():
            return False

        def _continue() -> None:
            v = self._view
            if v is None:
                return
            m = v.model()
            if m is None or not target.isValid():
                return
            sm = v.selectionModel()
            v.setCurrentIndex(target)
            if sm is not None:
                flags = QItemSelectionModel.SelectionFlag.ClearAndSelect
                if (
                    v.selectionBehavior()
                    == QAbstractItemView.SelectionBehavior.SelectRows
                ):
                    flags |= QItemSelectionModel.SelectionFlag.Rows
                sm.select(target, flags)
            v.setFocus(Qt.FocusReason.OtherFocusReason)
            v.scrollTo(target, QAbstractItemView.ScrollHint.EnsureVisible)
            if target.flags() & Qt.ItemFlag.ItemIsEditable:
                v.edit(target)

        self._finish_edit(editor)
        QTimer.singleShot(10, _continue)
        return True

    def _handle_editor_key(self, editor: QWidget, event) -> bool:
        view = self._view
        if view is None:
            return False
        mods = event.modifiers()
        if mods & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
            | Qt.KeyboardModifier.ShiftModifier
        ):
            return False
        key = event.key()
        idx = view.currentIndex()
        if not idx.isValid():
            return False
        model = view.model()
        if model is None:
            return False
        row, col = idx.row(), idx.column()
        nrows = _grid_data_row_count(view)
        ncols = model.columnCount()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            nxt = self._next_editable_cell(model, row, col, nrows, ncols)
            if nxt is None:
                self._finish_edit(editor)
                return True
            next_row, next_col = nxt
            return self._navigate_from_editor(editor, next_row, next_col)

        # 左右：僅在游標到邊界時換格，否則保留欄內編輯
        if key == Qt.Key.Key_Left:
            if isinstance(editor, QLineEdit):
                if editor.hasSelectedText() or editor.cursorPosition() > 0:
                    return False
            nc = col - 1
            if nc < 0:
                return False
            return self._navigate_from_editor(editor, row, nc)
        if key == Qt.Key.Key_Right:
            if isinstance(editor, QLineEdit):
                if editor.hasSelectedText() or editor.cursorPosition() < len(editor.text()):
                    return False
            nc = col + 1
            if nc >= ncols:
                return False
            return self._navigate_from_editor(editor, row, nc)

        arrow_map = {
            Qt.Key.Key_Up: (-1, 0),
            Qt.Key.Key_Down: (1, 0),
        }
        if key in arrow_map:
            dr, dc = arrow_map[key]
            nr, nc = row + dr, col + dc
            if 0 <= nr < nrows and 0 <= nc < ncols:
                return self._navigate_from_editor(editor, nr, nc)
            return False
        return False

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if (
            self._view is not None
            and event.type() == QEvent.Type.KeyPress
            and isinstance(obj, QLineEdit)
        ):
            if self._handle_editor_key(obj, event):
                return True
        return super().eventFilter(obj, event)


def _grid_cell_delegate(
    view: Optional[QAbstractItemView] = None,
    base_dir: Optional[str] = None,
) -> GridCellDelegate:
    """每個 QTableView 須使用獨立 delegate，不可共用（否則 commitData/closeEditor 警告）。"""
    return GridCellDelegate(view, base_dir=base_dir)


def _ensure_grid_cell_delegate(
    view: QAbstractItemView, base_dir: Optional[str] = None
) -> None:
    """此 view 僅設定一次 GridCellDelegate，避免重設時觸發 closeEditor 警告。"""
    delegate = view.itemDelegate()
    if isinstance(delegate, GridCellDelegate):
        delegate.set_view(view)
        if base_dir:
            delegate._base_dir = base_dir
        return
    view.setItemDelegate(_grid_cell_delegate(view, base_dir=base_dir))


def _end_grid_inplace_edit(view: QAbstractItemView) -> None:
    """換列／重載模型前先結束就地編輯，避免 commitData 指向錯誤 view。"""
    if view.state() != QAbstractItemView.State.EditingState:
        return
    view.clearFocus()
    if view.state() == QAbstractItemView.State.EditingState:
        view.setState(QAbstractItemView.State.NoState)


def _grid_column_text_alignment(field_name: str, data_format: str, data_type: str) -> int:
    """與輸入表單一致：文字／日期靠左，數字靠右。"""
    if is_boolean_data_type(data_type) or is_string_data_type(data_type):
        return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if (
        is_date_data_type(data_type)
        or is_date_field(field_name)
        or data_format_looks_like_date(data_format)
    ):
        return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if guess_number_kind(field_name, data_format, data_type) is not None:
        return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


def _physical_field_index(physical_fields: List[str], column_name: str) -> Optional[int]:
    want = column_name.strip().upper()
    for i, name in enumerate(physical_fields):
        if name.strip().upper() == want:
            return i
    return None


def _master_key_from_physical_row(
    physical_fields: Sequence[str],
    row: Sequence[str],
    *,
    key_column: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """自主檔實體列解析 TX 過濾鍵（欄名, 值）。"""
    candidates: List[str] = []
    for c in ((key_column or "").strip(), "TX_KEY", "ID"):
        if c and c.upper() not in [x.upper() for x in candidates]:
            candidates.append(c)
    for col in candidates:
        idx = _physical_field_index(list(physical_fields), col)
        if idx is None or idx >= len(row):
            continue
        val = str(row[idx] or "").strip()
        if val:
            return str(physical_fields[idx]), val
    return None, None


def _clear_tx_rows_master_keys(
    rows: List[List[str]],
    physical_fields: Sequence[str],
    *,
    key_column: str = "",
) -> List[List[str]]:
    """複製明細：清空 TX 表內主檔鍵欄，待儲存時寫入新鍵。"""
    key_cols: List[str] = []
    for c in ((key_column or "").strip(), "TX_KEY", "ID"):
        if c and c.upper() not in [x.upper() for x in key_cols]:
            key_cols.append(c)
    key_idx = {
        i
        for col in key_cols
        for i in [_physical_field_index(list(physical_fields), col)]
        if i is not None
    }
    if not key_idx:
        return [list(r) for r in rows]
    out: List[List[str]] = []
    for row in rows:
        r = list(row)
        for i in key_idx:
            if i < len(r):
                r[i] = ""
        out.append(r)
    return out


def _form_label_caption(raw_title: str) -> str:
    """輸入介面標題：結尾一律為英文冒號 ':'（先去掉既有的 :／：／︰ 再補上，避免重複）。"""
    t = (raw_title or "").strip()
    if not t:
        return ""
    while len(t) > 0 and t[-1] in (":", "：", "︰"):
        t = t[:-1].rstrip()
    return f"{t}:"


def _apply_uniform_form_label_widths(
    labels_by_field: Dict[str, QLabel],
    raw_title_by_field: Dict[str, str],
    base_dir: Optional[str] = None,
    layout_mode: str = FORM_LAYOUT_DEFAULT,
) -> None:
    """
    依表單標題 pt 粗體量測所有欄位標題，統一標題欄寬；標題文字一律靠右對齊（含備註／長文字）。
    若單行超過上限寬度則換行顯示，避免截斷。
    """
    if not labels_by_field:
        return
    font = QFont()
    font.setPointSize(get_ui_font_settings(base_dir).form_label_pt)
    font.setWeight(QFont.Weight.Bold)
    fm = QFontMetrics(font)
    fixed_w = _form_dims_for_mode(layout_mode)[0]
    for fld, label in labels_by_field.items():
        cap = _form_label_caption(raw_title_by_field.get(fld, ""))
        label.setFixedWidth(fixed_w)
        if cap and fm.horizontalAdvance(cap) + 6 > fixed_w:
            label.setWordWrap(True)
            label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
            )
        else:
            label.setWordWrap(False)
            label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )


def _apply_form_field_text_alignment(
    field: str, f_fmt: str, editor: QWidget, data_type: str = ""
) -> None:
    """標題另設；此處設定輸入區：一般文字與日期靠左，數字欄靠右。"""
    if isinstance(editor, QTextEdit):
        editor.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        return
    if isinstance(editor, QDateEdit):
        editor.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        return
    if isinstance(editor, QLineEdit):
        if is_date_field(field) or data_format_looks_like_date(f_fmt):
            editor.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
        elif guess_number_kind(field, f_fmt, data_type) is not None:
            editor.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        else:
            editor.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )


def _form_uses_date_editor(field: str, f_fmt: str, f_typ: str) -> bool:
    """依 columns.DATA_TYPE 優先決定是否使用日期輸入。"""
    if is_date_data_type(f_typ):
        return True
    if (
        is_boolean_data_type(f_typ)
        or is_numeric_data_type(f_typ)
        or is_string_data_type(f_typ)
    ):
        return False
    return bool((f_fmt or "").strip()) or is_date_field(field) or data_format_looks_like_date(
        f_fmt
    )


def _form_editor_text(editor: QWidget) -> str:
    if isinstance(editor, QComboBox):
        return (editor.currentText() or "").strip()
    if isinstance(editor, QLineEdit):
        return editor.text().strip()
    if isinstance(editor, QDateEdit):
        return editor.date().toString(APP_DATE_QT_FORMAT)
    if isinstance(editor, QTextEdit):
        return editor.toPlainText().strip()
    return ""


def _create_form_editor(
    field: str,
    f_fmt: str,
    f_typ: str,
    *,
    combo_choices: Optional[Sequence[str]] = None,
    use_combo: bool = False,
) -> QWidget:
    """依 DATA_TYPE／DATA_FORMAT／COMBO_LIST 建立輸入控制項。"""
    if use_combo or combo_choices:
        cb = QComboBox()
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        seen = set()
        for opt in list(combo_choices or []):
            s = str(opt or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            cb.addItem(s)
        cb.setFixedHeight(_FORM_EDITOR_HEIGHT_PX)
        return cb
    if _is_long_text_field(field, f_typ):
        editor: QWidget = QTextEdit()
        editor.setFixedHeight(_form_long_text_height_px())
        return editor
    if _form_uses_date_editor(field, f_fmt, f_typ):
        return FormNavDateEdit()
    return QLineEdit()


def _init_form_editor_value(
    editor: QWidget, field: str, val: str, f_fmt: str, f_typ: str
) -> None:
    """表單初值依 DATA_TYPE 格式化顯示（與 Grid 一致）。"""
    if isinstance(editor, QComboBox):
        text = format_cell_display(field, val or "", f_fmt, f_typ)
        idx = editor.findText(text)
        if idx >= 0:
            editor.setCurrentIndex(idx)
        else:
            editor.setEditText(text)
        return
    if isinstance(editor, QLineEdit):
        editor.setText(format_cell_display(field, val or "", f_fmt, f_typ))
        _apply_form_field_text_alignment(field, f_fmt, editor, f_typ)
    elif isinstance(editor, QDateEdit):
        d = parse_qdate(val or "", f_fmt)
        if d is not None:
            editor.setDate(QDate(d.year, d.month, d.day))
        _apply_form_field_text_alignment(field, f_fmt, editor, f_typ)
    elif isinstance(editor, QTextEdit):
        editor.setPlainText(format_cell_display(field, val or "", f_fmt, f_typ))
        _apply_form_field_text_alignment(field, f_fmt, editor, f_typ)


def _apply_form_values_to_editors(
    editors: Dict[str, QWidget],
    field_names: List[str],
    values: Dict[str, str],
    table_name: str,
    data_dict: DataDictionary,
) -> None:
    for field in field_names:
        editor = editors.get(field)
        if editor is None:
            continue
        f_fmt = data_dict.get_data_format(table_name, field)
        f_typ = data_dict.get_data_type(table_name, field)
        _init_form_editor_value(editor, field, values.get(field, ""), f_fmt, f_typ)


def _is_long_text_field(field_name: str, data_type: str = "") -> bool:
    """欄名或資料型別暗示備註／長文字時，表單改為 QTextEdit（佔 2 欄 × 2 行）。"""
    s = (field_name or "").lower()
    if any(k in s for k in ("note", "remark", "memo", "備註", "說明")):
        return True
    dt = (data_type or "").strip().upper()
    if not dt:
        return False
    if dt in ("MEMO", "LONGTEXT", "NTEXT"):
        return True
    return "MEMO" in dt


def _form_long_text_height_px(layout_mode: str = FORM_LAYOUT_DEFAULT) -> int:
    """長文字高度：一般欄高 × 2 行 + 列間距。"""
    _, _, editor_h = _form_dims_for_mode(layout_mode)
    rows = max(1, int(_FORM_LONG_TEXT_ROW_SPAN))
    return editor_h * rows + _FORM_GRID_V_SPACING_PX * max(0, rows - 1)


# 預設／規劃輸入介面常數見檔案開頭
_FORM_LAYOUT_MODE_CACHE: Optional[str] = None


def _form_layout_mode_path(base_dir: Optional[str]) -> Optional[str]:
    if not base_dir:
        return None
    return os.path.join(os.path.abspath(base_dir), "form_layout_mode.json")


def get_form_layout_mode(base_dir: Optional[str] = None) -> str:
    """讀取目前輸入介面模式（default / planned）。"""
    global _FORM_LAYOUT_MODE_CACHE
    if _FORM_LAYOUT_MODE_CACHE in (FORM_LAYOUT_DEFAULT, FORM_LAYOUT_PLANNED):
        return _FORM_LAYOUT_MODE_CACHE
    path = _form_layout_mode_path(base_dir)
    if path and os.path.isfile(path):
        try:
            import json

            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            mode = str((raw or {}).get("mode") or "").strip().lower()
            if mode in (FORM_LAYOUT_DEFAULT, FORM_LAYOUT_PLANNED):
                _FORM_LAYOUT_MODE_CACHE = mode
                return mode
        except Exception:
            pass
    _FORM_LAYOUT_MODE_CACHE = FORM_LAYOUT_DEFAULT
    return FORM_LAYOUT_DEFAULT


def set_form_layout_mode(mode: str, base_dir: Optional[str] = None) -> str:
    """設定並持久化輸入介面模式。"""
    global _FORM_LAYOUT_MODE_CACHE
    m = (mode or "").strip().lower()
    if m not in (FORM_LAYOUT_DEFAULT, FORM_LAYOUT_PLANNED):
        m = FORM_LAYOUT_DEFAULT
    _FORM_LAYOUT_MODE_CACHE = m
    path = _form_layout_mode_path(base_dir)
    if path:
        try:
            import json

            with open(path, "w", encoding="utf-8") as f:
                json.dump({"mode": m}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return m


def _form_layout_spec(
    total_fields: int, mode: str = FORM_LAYOUT_DEFAULT
) -> Tuple[int, int, int]:
    """回傳 (cols_per_row, fields_per_page, rows_per_page)。"""
    n = max(0, int(total_fields or 0))
    if (mode or "").strip().lower() == FORM_LAYOUT_PLANNED:
        if n <= 15:
            return 3, 15, 5
        return 5, 25, 5
    if n <= 20:
        return 2, 20, _FORM_ROWS_PER_PAGE
    return 3, 30, _FORM_ROWS_PER_PAGE


def _form_label_align_vcenter() -> Qt.AlignmentFlag:
    # 標題在左欄、文字靠右，貼近右側輸入欄
    return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def _form_label_align_top() -> Qt.AlignmentFlag:
    return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop


def _form_label_align_above() -> Qt.AlignmentFlag:
    return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def _form_detach_widget(w: Optional[QWidget]) -> None:
    """切換版面前先脫離舊 layout，避免重建時被銷毀。"""
    if w is None:
        return
    try:
        p = w.parentWidget()
        if p is not None:
            lay = p.layout()
            if lay is not None:
                lay.removeWidget(w)
        w.setParent(None)
    except Exception:
        try:
            w.setParent(None)
        except Exception:
            pass


def _form_add_short_field_pair(
    grid: QGridLayout,
    row: int,
    col_slot: int,
    label: QLabel,
    editor: QWidget,
) -> None:
    """一般欄：標題在左、輸入在右。"""
    label_col = col_slot * 2
    editor_col = label_col + 1
    label.setAlignment(_form_label_align_vcenter())
    grid.addWidget(label, row, label_col, alignment=_form_label_align_vcenter())
    grid.addWidget(editor, row, editor_col)


def _form_row_for_long_text(row: int, col_slot: int, *, span_cols: int = 2) -> int:
    """上一列若剩餘欄位不足長文字橫跨寬度，改從下一列開始。"""
    if col_slot > 0:
        return row + 1
    _ = span_cols
    return row


def _form_add_long_text_block(
    grid: QGridLayout,
    row: int,
    label: QLabel,
    editor: QWidget,
    *,
    cols_per_row: int,
    layout_mode: str = FORM_LAYOUT_DEFAULT,
) -> Tuple[int, int]:
    """備註／長文字：佔 2 欄 × 2 行；回傳 (下一列, 下一欄槽)。"""
    span_cols = min(_FORM_LONG_TEXT_COL_SPAN, max(1, int(cols_per_row)))
    span_rows = max(1, int(_FORM_LONG_TEXT_ROW_SPAN))
    grid_span = span_cols * 2
    h = _form_long_text_height_px(layout_mode)
    text_ed = _form_long_text_editor_from_display(editor)
    if text_ed is not None:
        text_ed.setFixedHeight(h)
        text_ed.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    label.setAlignment(_form_label_align_top())
    editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    grid.addWidget(label, row, 0, span_rows, 1, alignment=_form_label_align_top())
    grid.addWidget(editor, row, 1, span_rows, max(1, grid_span - 1))
    # 右側若尚有欄位槽，本實作不插入短欄，直接跳至長文字下方，版面較單純
    return row + span_rows, 0


def _form_make_stacked_cell(label: QLabel, editor: QWidget) -> QWidget:
    """規劃介面：標題在上、輸入在下。"""
    cell = QWidget()
    lay = QVBoxLayout(cell)
    lay.setContentsMargins(0, 0, 2, 2)
    lay.setSpacing(2)
    label.setAlignment(_form_label_align_above())
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    editor.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    lay.addWidget(label, 0, Qt.AlignmentFlag.AlignLeft)
    lay.addWidget(editor, 0, Qt.AlignmentFlag.AlignLeft)
    cell.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return cell


def _form_label_column_width(labels_by_field: Optional[Dict[str, QLabel]] = None) -> int:
    if labels_by_field:
        for lb in labels_by_field.values():
            w = lb.width()
            if w > 0:
                return w
    return _FORM_LABEL_WIDTH_DEFAULT_PX


def _form_dims_for_mode(layout_mode: str) -> Tuple[int, int, int]:
    """回傳 (label_w, editor_w, editor_h)。"""
    if (layout_mode or "").strip().lower() == FORM_LAYOUT_PLANNED:
        return (
            _FORM_LABEL_WIDTH_PLANNED_PX,
            _FORM_EDITOR_WIDTH_PLANNED_PX,
            _FORM_EDITOR_HEIGHT_PX,
        )
    return (
        _FORM_LABEL_WIDTH_DEFAULT_PX,
        _FORM_EDITOR_WIDTH_DEFAULT_PX,
        _FORM_EDITOR_HEIGHT_PX,
    )


def _apply_form_label_widths_for_mode(
    labels_by_field: Dict[str, QLabel],
    raw_title_by_field: Dict[str, str],
    *,
    base_dir: Optional[str],
    layout_mode: str,
) -> None:
    if (layout_mode or "").strip().lower() == FORM_LAYOUT_PLANNED:
        label_w = _form_dims_for_mode(layout_mode)[0]
        for lb in labels_by_field.values():
            lb.setMinimumWidth(0)
            lb.setMaximumWidth(16777215)
            lb.setFixedWidth(label_w)
            lb.setAlignment(_form_label_align_above())
        return
    _apply_uniform_form_label_widths(
        labels_by_field,
        raw_title_by_field,
        base_dir,
        layout_mode=layout_mode,
    )


def _form_apply_grid_column_stretch(
    grid: QGridLayout,
    labels_by_field: Optional[Dict[str, QLabel]] = None,
    *,
    grid_ncols: int,
    editor_width: int,
) -> None:
    """標題／輸入欄固定寬並靠左；多餘寬度由右側空白欄吸收。"""
    label_w = _form_label_column_width(labels_by_field)
    for c in range(0, grid_ncols, 2):
        grid.setColumnStretch(c, 0)
        grid.setColumnMinimumWidth(c, label_w)
    for c in range(1, grid_ncols, 2):
        grid.setColumnStretch(c, 0)
        grid.setColumnMinimumWidth(c, editor_width)
    # 右側 stretch 欄：二／三欄內容向左排列，不均分整列寬度
    grid.setColumnStretch(grid_ncols, 1)


def _form_apply_planned_grid_stretch(
    grid: QGridLayout, *, cols_per_row: int, editor_width: int
) -> None:
    """規劃介面：每欄固定寬，右側空白吸收多餘寬度。"""
    for c in range(cols_per_row):
        grid.setColumnStretch(c, 0)
        grid.setColumnMinimumWidth(c, editor_width)
    grid.setColumnStretch(cols_per_row, 1)


def _form_fill_empty_slots(
    grid: QGridLayout,
    *,
    row: int,
    col_slot: int,
    cols_per_row: int,
    rows_per_page: int,
    layout_mode: str = FORM_LAYOUT_DEFAULT,
) -> None:
    """不足一頁時以空白槽保留版面，不自動縮放。"""
    planned = (layout_mode or "").strip().lower() == FORM_LAYOUT_PLANNED
    _, editor_w, editor_h = _form_dims_for_mode(layout_mode)
    while row < rows_per_page:
        filler = QWidget()
        filler_layout = QHBoxLayout(filler)
        filler_layout.setContentsMargins(0, 0, 0, 0)
        filler_layout.addStretch(1)
        if planned:
            filler.setMinimumSize(editor_w, editor_h + 30)
            grid.addWidget(filler, row, col_slot)
        else:
            grid.addWidget(filler, row, col_slot * 2, 1, 2)
        if col_slot == cols_per_row - 1:
            col_slot = 0
            row += 1
        else:
            col_slot += 1


def _disable_ime(widget: QWidget) -> None:
    """偏向英文（Latin）輸入：保留輸入法可用，但優先 Latin 模式。"""
    try:
        widget.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
    except Exception:
        pass


def _split_fields_by_edit_tab(
    field_meta: List[Dict[str, object]],
    table_name: str,
    data_dict: DataDictionary,
    fallback_page_size: int,
) -> List[tuple[str, List[Dict[str, object]]]]:
    """
    依 columns.EDIT_TAB 分組欄位；無 EDIT_TAB 的欄位再按固定頁大小補到後續 TAB。
    回傳 [(tab_key, fields)]，tab_key 為空字串代表沿用預設 TAB 標題規則。
    """
    groups: Dict[str, List[Dict[str, object]]] = {}
    ungrouped: List[Dict[str, object]] = []
    for m in field_meta:
        field = str(m.get("field", "")).strip()
        tab_key = data_dict.get_edit_tab(table_name, field).strip()
        if tab_key:
            groups.setdefault(tab_key, []).append(m)
        else:
            ungrouped.append(m)

    if not groups:
        return []

    out: List[tuple[str, List[Dict[str, object]]]] = []
    page_size = fallback_page_size if fallback_page_size > 0 else 25
    for key, vals in groups.items():
        if not vals:
            continue
        # EDIT_TAB 群組超過一頁容量時再切分
        if len(vals) <= page_size:
            out.append((key, vals))
            continue
        for i in range(0, len(vals), page_size):
            chunk = vals[i : i + page_size]
            page_idx = i // page_size
            tab_key = key if page_idx == 0 else f"{key} - {page_idx + 1}"
            out.append((tab_key, chunk))
    for i in range(0, len(ungrouped), page_size):
        out.append(("", ungrouped[i : i + page_size]))
    return out


def _edit_tab_key_is_index(tab_key: str) -> bool:
    """純數字（或「1 - 2」）的 EDIT_TAB 只用於分頁，不當成自訂標題。"""
    key = (tab_key or "").strip()
    if not key:
        return True
    if key.isdigit():
        return True
    parts = [p.strip() for p in key.split("-")]
    return len(parts) == 2 and all(p.isdigit() for p in parts)


def _form_tab_title_for_key(
    tab_key: str,
    idx1: int,
    total_tabs: int,
    *,
    lang: LanguageCode,
    menu_base: str,
) -> str:
    """EDIT_TAB 有名稱時用其名稱；純數字則沿用「資料 / Data」。"""
    key = (tab_key or "").strip()
    if key and not _edit_tab_key_is_index(key):
        return key
    base = (menu_base or "").strip()
    if lang == "CHN":
        if total_tabs <= 1:
            return f"{base} 資 料".strip() if base else "資 料"
        return f"{base} 資 料 - {idx1}".strip() if base else f"資 料 - {idx1}"
    if total_tabs <= 1:
        return f"{base} Data".strip() if base else "Data"
    return f"{base} Data - {idx1}".strip() if base else f"Data - {idx1}"


def _form_pages_from_meta(
    field_meta: List[Dict[str, object]],
    *,
    table_name: str,
    data_dict: DataDictionary,
    layout_mode: str,
) -> Tuple[List[List[Dict[str, object]]], List[str], int, int]:
    """依模式與 EDIT_TAB 切分頁；回傳 (pages, tab_keys, cols_per_row, rows_per_page)。"""
    cols_per_row, fields_per_page, rows_per_page = _form_layout_spec(
        len(field_meta), layout_mode
    )
    edit_tab_groups = _split_fields_by_edit_tab(
        field_meta,
        table_name,
        data_dict,
        fallback_page_size=fields_per_page,
    )
    if edit_tab_groups:
        pages = [vals for _, vals in edit_tab_groups] or [[]]
        tab_keys = [k for k, _ in edit_tab_groups]
    else:
        pages = [
            field_meta[i : i + fields_per_page]
            for i in range(0, len(field_meta), fields_per_page)
        ] or [[]]
        tab_keys = [""] * len(pages)
    return pages, tab_keys, cols_per_row, rows_per_page


def _build_fixed_form_page(
    page_fields: List[Dict[str, object]],
    *,
    cols_per_row: int,
    rows_per_page: int,
    labels_by_field: Optional[Dict[str, QLabel]] = None,
    layout_mode: str = FORM_LAYOUT_DEFAULT,
) -> QWidget:
    """依預設（左標右欄）或規劃（上標下欄）規格建一頁；不足槽位留空。"""
    planned = (layout_mode or "").strip().lower() == FORM_LAYOUT_PLANNED
    _, editor_w, _editor_h = _form_dims_for_mode(layout_mode)
    page = QWidget()
    grid = QGridLayout(page)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(2 if not planned else 8)
    grid.setVerticalSpacing(_FORM_GRID_V_SPACING_PX)
    grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    # 重建前先脫離，避免舊 parent 銷毀時帶走 label／editor
    for m in page_fields:
        _form_detach_widget(m.get("display") or m.get("editor"))  # type: ignore[arg-type]
        _form_detach_widget(m.get("label"))  # type: ignore[arg-type]

    row = 0
    col_slot = 0
    if planned:
        h_space = 8
        for m in page_fields:
            label = m["label"]  # type: ignore[assignment]
            raw_editor = m.get("editor")
            display = m.get("display") or raw_editor  # type: ignore[assignment]
            is_long = bool(m.get("is_long"))
            if is_long:
                span_cols = min(_FORM_LONG_TEXT_COL_SPAN, max(1, cols_per_row))
                span_rows = max(1, int(_FORM_LONG_TEXT_ROW_SPAN))
                row = _form_row_for_long_text(row, col_slot, span_cols=span_cols)
                wide_w = editor_w * span_cols + h_space * max(0, span_cols - 1)
                has_lookup_wrap = (
                    isinstance(display, QWidget) and display is not raw_editor
                )
                text_w = (
                    max(40, wide_w - _lookup_wrap_button_slot_px())
                    if has_lookup_wrap
                    else wide_w
                )
                if isinstance(raw_editor, QTextEdit):
                    raw_editor.setFixedHeight(_form_long_text_height_px(layout_mode))
                    raw_editor.setFixedWidth(text_w)
                    raw_editor.setMinimumWidth(text_w)
                    raw_editor.setSizePolicy(
                        QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
                    )
                if has_lookup_wrap:
                    display.setFixedWidth(wide_w)
                    display.setMinimumWidth(wide_w)
                    display.setSizePolicy(
                        QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
                    )
                label.setFixedWidth(wide_w)
                label.setMinimumWidth(wide_w)
                label.setAlignment(_form_label_align_above())
                cell = _form_make_stacked_cell(label, display)  # type: ignore[arg-type]
                cell.setFixedWidth(wide_w)
                cell.setMinimumWidth(wide_w)
                cell.setSizePolicy(
                    QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
                )
                grid.addWidget(cell, row, 0, span_rows, span_cols)
                row += span_rows
                col_slot = 0
                continue
            cell = _form_make_stacked_cell(label, display)  # type: ignore[arg-type]
            grid.addWidget(cell, row, col_slot)
            if col_slot == cols_per_row - 1:
                col_slot = 0
                row += 1
            else:
                col_slot += 1
        _form_fill_empty_slots(
            grid,
            row=row,
            col_slot=col_slot,
            cols_per_row=cols_per_row,
            rows_per_page=rows_per_page,
            layout_mode=FORM_LAYOUT_PLANNED,
        )
        _form_apply_planned_grid_stretch(grid, cols_per_row=cols_per_row, editor_width=editor_w)
        grid.setRowStretch(rows_per_page, 1)
        return page

    for m in page_fields:
        label = m["label"]  # type: ignore[assignment]
        editor = m.get("display") or m["editor"]  # type: ignore[assignment]
        is_long = bool(m.get("is_long"))
        if is_long:
            span_cols = min(_FORM_LONG_TEXT_COL_SPAN, max(1, cols_per_row))
            row = _form_row_for_long_text(row, col_slot, span_cols=span_cols)
            row, col_slot = _form_add_long_text_block(
                grid,
                row,
                label,
                editor,
                cols_per_row=cols_per_row,
                layout_mode=layout_mode,
            )
            continue
        _form_add_short_field_pair(grid, row, col_slot, label, editor)
        if col_slot == cols_per_row - 1:
            col_slot = 0
            row += 1
        else:
            col_slot += 1

    _form_fill_empty_slots(
        grid,
        row=row,
        col_slot=col_slot,
        cols_per_row=cols_per_row,
        rows_per_page=rows_per_page,
        layout_mode=FORM_LAYOUT_DEFAULT,
    )
    grid_ncols = cols_per_row * 2
    _form_apply_grid_column_stretch(
        grid, labels_by_field, grid_ncols=grid_ncols, editor_width=editor_w
    )
    grid.setRowStretch(rows_per_page, 1)
    return page


def _populate_form_tab_widget(
    tab_widget: QTabWidget,
    field_meta: List[Dict[str, object]],
    *,
    table_name: str,
    data_dict: DataDictionary,
    layout_mode: str,
    labels_by_field: Optional[Dict[str, QLabel]],
    tab_title_fn: Callable[[str, int, int], str],
) -> List[str]:
    """清空並依模式重建表單 TAB；回傳 tab_keys。"""
    # 先脫離所有欄位，避免 clear 銷毀 page 時帶走 editors
    for m in field_meta:
        _form_detach_widget(m.get("display") or m.get("editor"))  # type: ignore[arg-type]
        _form_detach_widget(m.get("label"))  # type: ignore[arg-type]
    while tab_widget.count():
        w = tab_widget.widget(0)
        tab_widget.removeTab(0)
        if w is not None:
            w.deleteLater()

    pages, tab_keys, cols_per_row, rows_per_page = _form_pages_from_meta(
        field_meta,
        table_name=table_name,
        data_dict=data_dict,
        layout_mode=layout_mode,
    )
    total_tabs = len(pages)
    for i, page_fields in enumerate(pages, start=1):
        key = tab_keys[i - 1] if (i - 1) < len(tab_keys) else ""
        tab_widget.addTab(
            _build_fixed_form_page(
                page_fields,
                cols_per_row=cols_per_row,
                rows_per_page=rows_per_page,
                labels_by_field=labels_by_field,
                layout_mode=layout_mode,
            ),
            tab_title_fn(key, i, total_tabs),
        )
    from core.ui_theme import apply_tab_title_colors

    apply_tab_title_colors(tab_widget)
    return tab_keys


_LOOKUP_BTN_STYLE = ""  # 由 lookup_button_qss() 動態產生


def _wrap_lookup_field_editor(
    editor: QWidget,
    *,
    on_lookup: Callable[[], None],
    lang: LanguageCode,
) -> QWidget:
    """輸入欄右側加 Lookup 按鈕：寬與高皆等於輸入欄高度。"""
    wrap = QWidget()
    lay = QHBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    is_long = isinstance(editor, QTextEdit)
    # 長文字（備註）：輸入框伸展佔滿，按鈕固定貼在右側
    lay.addWidget(editor, 1 if is_long else 0)
    btn = QPushButton("…")
    btn.setToolTip("查找" if lang == "CHN" else "Lookup")
    btn.setStyleSheet(lookup_button_qss())
    btn.setFlat(False)
    h = _FORM_EDITOR_HEIGHT_PX
    btn.setFixedSize(h, h)
    btn.setMinimumSize(h, h)
    btn.setMaximumSize(h, h)
    if isinstance(editor, (QLineEdit, QDateEdit)):
        editor.setFixedHeight(h)
    btn.clicked.connect(on_lookup)
    btn_align = (
        Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        if is_long
        else Qt.AlignmentFlag.AlignVCenter
    )
    lay.addWidget(btn, 0, btn_align)
    if is_long:
        wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    else:
        wrap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return wrap


def _lookup_wrap_button_slot_px() -> int:
    """LOOKUP 按鈕佔用寬度（鈕寬 + wrap spacing）。"""
    return _FORM_EDITOR_HEIGHT_PX + 2


def _form_long_text_editor_from_display(display: QWidget) -> Optional[QTextEdit]:
    if isinstance(display, QTextEdit):
        return display
    return display.findChild(QTextEdit) if isinstance(display, QWidget) else None


def reapply_grid_fonts(
    tv: QTableView, base_dir: Optional[str] = None
) -> None:
    """Grid 儲存格與欄位標題列字體變更後重新套用。"""
    bd = base_dir or _font_base_dir_for(tv)
    if not tv.objectName():
        tv.setObjectName("appGridTable")
    fm_cell, fm_hdr = _apply_grid_header_fonts(tv, bd)
    _ensure_grid_cell_delegate(tv, bd)
    hdr = tv.horizontalHeader()
    hdr.setObjectName("appGridHeader")
    hdr.updateGeometry()
    tv.viewport().update()


def reapply_form_fonts(
    labels: Dict[str, QLabel],
    editors: Dict[str, QWidget],
    *,
    base_dir: Optional[str] = None,
    table_name: str = "",
    data_dict: Optional[DataDictionary] = None,
    field_names: Optional[List[str]] = None,
    lang: LanguageCode = "CHN",
) -> None:
    """輸入表單標題與編輯欄字體變更後重新套用。"""
    bd = base_dir
    for label in labels.values():
        label.setStyleSheet(form_label_style(bd))
    for editor in editors.values():
        editor.setStyleSheet(form_editor_style(bd))
    if labels and data_dict and field_names:
        raw = {
            f: data_dict.get_title(table_name, f, lang) for f in field_names
        }
        _apply_uniform_form_label_widths(labels, raw, bd)


def _apply_form_editor_dimensions(
    editor: QWidget, layout_mode: str = FORM_LAYOUT_DEFAULT
) -> None:
    """輸入欄固定寬高（一般／日期／長文字）。"""
    _lw, editor_w, editor_h = _form_dims_for_mode(layout_mode)
    if isinstance(editor, (QLineEdit, QDateEdit, QComboBox)):
        editor.setFixedWidth(editor_w)
        editor.setFixedHeight(editor_h)
    elif isinstance(editor, QTextEdit):
        editor.setFixedHeight(_form_long_text_height_px(layout_mode))


# 日期顯示／儲存：見 core.display_format.APP_DATE_QT_FORMAT（yyyy/MM/dd）

# 工作頁功能按鈕：淺藍→天藍漸層、依文字寬度伸縮（對齊 Web 科幻面板感）
_WORK_ACTION_BTN_MIN_W = 120
_WORK_ACTION_BTN_MAX_W = 280
_WORK_ACTION_BTN_H = 36
_WORK_ACTION_BTN_PAD_X = 38
_WORK_ACTION_ICON_PX = 16
_WORK_ACTION_BUTTON_STYLE = ""  # 由 work_action_button_qss() 動態產生


def work_action_button_width(btn: QPushButton) -> int:
    fm = QFontMetrics(btn.font())
    text_w = fm.horizontalAdvance((btn.text() or "").strip())
    return max(
        _WORK_ACTION_BTN_MIN_W,
        min(_WORK_ACTION_BTN_MAX_W, text_w + _WORK_ACTION_BTN_PAD_X),
    )


def apply_work_action_button_style(btn: QPushButton) -> None:
    """功能列按鈕：科技風、寬度依目前文字（含圖示留白）。"""
    from PyQt6.QtCore import QSize

    btn.setStyleSheet(work_action_button_qss())
    btn.setIconSize(QSize(_WORK_ACTION_ICON_PX, _WORK_ACTION_ICON_PX))
    btn.setFixedSize(work_action_button_width(btn), _WORK_ACTION_BTN_H)


_NAV_BTN_W = 28
_NAV_BTN_H = 28
_NAV_ICON_PX = 16

# 圖示導覽鈕：較小、留白少（文字為空，僅顯示 standardIcon）
_NAV_ICON_BUTTON_STYLE = ""  # 由 nav_button_qss() 動態產生


def apply_nav_button_style(btn: QPushButton) -> None:
    """Grid 資料導覽：小方形按鈕 + 較小圖示（首筆/上筆/下筆/末筆）。"""
    btn.setStyleSheet(nav_button_qss())
    btn.setFixedSize(_NAV_BTN_W, _NAV_BTN_H)
    btn.setIconSize(QSize(_NAV_ICON_PX, _NAV_ICON_PX))


def _form_focus_widgets(
    field_names: List[str], editors: Dict[str, QWidget]
) -> List[QWidget]:
    out: List[QWidget] = []
    for f in field_names:
        w = editors.get(f)
        if isinstance(w, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
            out.append(w)
    return out


def _form_nav_mods_blocked(event) -> bool:
    """Ctrl／Alt／Meta／Shift 按下時不攔方向鍵（保留系統行為）。"""
    mods = event.modifiers()
    blocked = (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
        | Qt.KeyboardModifier.ShiftModifier
    )
    return bool(mods & blocked)


def _form_line_edit_of(editor: QWidget) -> Optional[QLineEdit]:
    """QLineEdit 本身，或 QDateEdit／QComboBox 內部行編輯。"""
    if isinstance(editor, QLineEdit):
        return editor
    if isinstance(editor, QDateEdit):
        kids = editor.findChildren(QLineEdit)
        return kids[0] if kids else None
    if isinstance(editor, QComboBox):
        le = editor.lineEdit()
        if le is not None:
            return le
        kids = editor.findChildren(QLineEdit)
        return kids[0] if kids else None
    return None


def _form_bind_composite_nav_proxy(
    host: QWidget,
    editor: QWidget,
    form_nav_proxy: Dict[QWidget, QWidget],
) -> None:
    """將 QDateEdit／QComboBox 內部 QLineEdit 掛上 host 的換欄 eventFilter。"""
    if not isinstance(editor, (QDateEdit, QComboBox)):
        return
    if isinstance(editor, FormNavDateEdit):
        editor.set_form_nav_filter_host(host)
    for child in editor.findChildren(QLineEdit):
        form_nav_proxy[child] = editor
        try:
            child.installEventFilter(host)
        except Exception:
            pass


def _form_resolve_nav_editor(
    obj: QWidget,
    form_nav_widgets: set,
    form_nav_proxy: Dict[QWidget, QWidget],
) -> Optional[QWidget]:
    """由實際收鍵控制項解析表單導覽用編輯器（含日期內部編輯列）。"""
    mapped = form_nav_proxy.get(obj)
    if mapped is not None:
        return mapped
    if obj in form_nav_widgets:
        return obj
    w: Optional[QWidget] = obj.parentWidget() if isinstance(obj, QWidget) else None
    while w is not None:
        if w in form_nav_widgets:
            if isinstance(obj, QLineEdit):
                form_nav_proxy[obj] = w
            return w
        w = w.parentWidget()
    return None


class FormNavDateEdit(QDateEdit):
    """
    表單日期欄：內部編輯列的 Enter／方向鍵交給表單換欄，
    避免只在年／月／日區段之間跳動。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat(APP_DATE_QT_FORMAT)
        self._form_nav_filter_host: Optional[QWidget] = None
        QTimer.singleShot(0, self._hook_inner_line_edit)

    def set_form_nav_filter_host(self, host: Optional[QWidget]) -> None:
        self._form_nav_filter_host = host
        self._hook_inner_line_edit()

    def _hook_inner_line_edit(self) -> None:
        host = self._form_nav_filter_host
        for child in self.findChildren(QLineEdit):
            try:
                child.installEventFilter(self)
            except Exception:
                pass
            if host is not None:
                try:
                    child.installEventFilter(host)
                except Exception:
                    pass
                proxy = getattr(host, "_form_nav_proxy", None)
                if isinstance(proxy, dict):
                    proxy[child] = self

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._hook_inner_line_edit()
        QTimer.singleShot(0, self._hook_inner_line_edit)

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if (
            isinstance(obj, QLineEdit)
            and event.type() == QEvent.Type.KeyPress
            and self._form_nav_filter_host is not None
        ):
            key = event.key()
            if key in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Down,
                Qt.Key.Key_Up,
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
            ):
                host = self._form_nav_filter_host
                # 以本日期欄為 obj 交給表單 page／dialog 的 eventFilter 換欄
                try:
                    if host.eventFilter(self, event):
                        return True
                except Exception:
                    pass
        return super().eventFilter(obj, event)


def _form_editor_caret_at_start(editor: QWidget) -> bool:
    le = _form_line_edit_of(editor)
    if le is not None:
        if le.hasSelectedText():
            return False
        return le.cursorPosition() <= 0
    if isinstance(editor, QTextEdit):
        c = editor.textCursor()
        if c.hasSelection():
            return False
        return c.position() <= 0
    return True


def _form_editor_caret_at_end(editor: QWidget) -> bool:
    le = _form_line_edit_of(editor)
    if le is not None:
        if le.hasSelectedText():
            return False
        return le.cursorPosition() >= len(le.text())
    if isinstance(editor, QTextEdit):
        c = editor.textCursor()
        if c.hasSelection():
            return False
        return c.position() >= len(editor.toPlainText())
    return True


def _form_editor_on_first_line(editor: QWidget) -> bool:
    if isinstance(editor, QTextEdit):
        c = editor.textCursor()
        return c.block() == editor.document().firstBlock()
    return True


def _form_editor_on_last_line(editor: QWidget) -> bool:
    if isinstance(editor, QTextEdit):
        c = editor.textCursor()
        return c.block() == editor.document().lastBlock()
    return True


def _form_should_nav_key(editor: QWidget, key: int) -> bool:
    """是否應用方向／Enter 換欄；否則交回控制項處理游標。"""
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        return not isinstance(editor, QTextEdit)
    if key == Qt.Key.Key_Left:
        return _form_editor_caret_at_start(editor)
    if key == Qt.Key.Key_Right:
        return _form_editor_caret_at_end(editor)
    if key == Qt.Key.Key_Up:
        return _form_editor_on_first_line(editor)
    if key == Qt.Key.Key_Down:
        return _form_editor_on_last_line(editor)
    return False


def _activate_form_tab_for_widget(
    form_tab_widget: Optional[QTabWidget], widget: QWidget
) -> None:
    if form_tab_widget is None:
        return
    w: Optional[QWidget] = widget
    while w is not None:
        idx = form_tab_widget.indexOf(w)
        if idx >= 0:
            form_tab_widget.setCurrentIndex(idx)
            return
        w = w.parentWidget()


def _focus_form_widget(widget: QWidget) -> None:
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    if isinstance(widget, QLineEdit):
        widget.selectAll()
    elif isinstance(widget, QDateEdit):
        le = _form_line_edit_of(widget)
        if le is not None:
            le.selectAll()
    elif isinstance(widget, QComboBox) and widget.lineEdit() is not None:
        widget.lineEdit().selectAll()


def _focus_next_form_field(
    field_names: List[str],
    editors: Dict[str, QWidget],
    obj: QWidget,
    tx_tabs: Optional[QTabWidget],
    save_button: Optional[QWidget],
    form_tab_widget: Optional[QTabWidget] = None,
) -> bool:
    """
    輸入表單：Enter／下鍵 → 下一欄（依 field_names 順序）。
    最後一欄之後：明細 Tab → 儲存鈕。
    """
    order = _form_focus_widgets(field_names, editors)
    if obj not in order:
        return False
    idx = order.index(obj)
    if idx + 1 < len(order):
        nxt = order[idx + 1]
        _activate_form_tab_for_widget(form_tab_widget, nxt)
        _focus_form_widget(nxt)
        return True
    if tx_tabs is not None:
        cw = tx_tabs.currentWidget()
        if cw is not None:
            cw.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
    if save_button is not None:
        save_button.setFocus(Qt.FocusReason.OtherFocusReason)
        return True
    return False


def _focus_prev_form_field(
    field_names: List[str],
    editors: Dict[str, QWidget],
    obj: QWidget,
    form_tab_widget: Optional[QTabWidget] = None,
) -> bool:
    """輸入表單：上鍵 → 上一欄（依 field_names 順序）。"""
    order = _form_focus_widgets(field_names, editors)
    if obj not in order:
        return False
    idx = order.index(obj)
    if idx <= 0:
        return False
    prev = order[idx - 1]
    _activate_form_tab_for_widget(form_tab_widget, prev)
    _focus_form_widget(prev)
    return True


def _handle_form_field_key_nav(
    field_names: List[str],
    editors: Dict[str, QWidget],
    form_nav_widgets: set,
    obj: QWidget,
    event,
    tx_tabs: Optional[QTabWidget],
    save_button: Optional[QWidget],
    form_tab_widget: Optional[QTabWidget] = None,
) -> bool:
    if _form_nav_mods_blocked(event):
        return False
    if obj not in form_nav_widgets:
        return False
    key = event.key()
    if not _form_should_nav_key(obj, key):
        return False
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Down, Qt.Key.Key_Right):
        return _focus_next_form_field(
            field_names,
            editors,
            obj,
            tx_tabs,
            save_button,
            form_tab_widget,
        )
    if key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
        return _focus_prev_form_field(
            field_names, editors, obj, form_tab_widget
        )
    return False


def _form_field_has_search_ret(
    data_dict: DataDictionary, table_name: str, field: str
) -> bool:
    search_ret = (data_dict.get_search_ret(table_name, field) or "").strip()
    if not search_ret or search_ret.upper() in {
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
        return False
    lookup_db, lookup_key, _ret = data_dict.get_lookup(table_name, field)
    return bool((lookup_db or "").strip() and (lookup_key or "").strip())


def apply_form_field_search_ret(
    *,
    host: QWidget,
    data_dict: DataDictionary,
    backend: Optional[object],
    table_name: str,
    field: str,
    editors: Dict[str, QWidget],
    lang: LanguageCode,
) -> bool:
    """
    輸入欄結束編輯：LOOKUP_DB／LOOKUP_KEY 查找後，
    依 SEARCH_RET「左邊=目標欄／右邊=LOOKUP欄」回存。
    回傳 False 表示找不到（已提示）；True 表示成功或無需處理。
    """
    from core.search_ret_lookup import resolve_input_search_ret_for_field

    if getattr(host, "_search_ret_applying", False):
        return True
    w = editors.get(field)
    if not isinstance(w, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
        return True
    text = _form_editor_text(w)
    if not text:
        return True
    if not _form_field_has_search_ret(data_dict, table_name, field):
        return True

    mapped, err = resolve_input_search_ret_for_field(
        data_dict=data_dict,
        backend=backend,  # type: ignore[arg-type]
        table_name=table_name,
        source_field=field,
        input_value=text,
        lang=lang,
    )
    title = "輸入" if lang == "CHN" else "Input"
    if err:
        QMessageBox.information(host, title, err)
        if isinstance(w, QLineEdit):
            w.selectAll()
        elif isinstance(w, QComboBox) and w.lineEdit() is not None:
            w.lineEdit().selectAll()
        w.setFocus(Qt.FocusReason.OtherFocusReason)
        return False
    if not mapped:
        return True

    host._search_ret_applying = True  # type: ignore[attr-defined]
    try:
        for dest, value in mapped:
            dest_w = editors.get(dest)
            if dest_w is None and (dest or "").strip().upper() == (field or "").strip().upper():
                dest_w = w
                dest = field
            if dest_w is None:
                continue
            f_fmt = data_dict.get_data_format(table_name, dest)
            f_typ = data_dict.get_data_type(table_name, dest)
            if isinstance(dest_w, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
                _init_form_editor_value(dest_w, dest, value, f_fmt, f_typ)
    finally:
        host._search_ret_applying = False  # type: ignore[attr-defined]
    return True


def install_form_search_ret_hooks(
    host: QWidget,
    *,
    data_dict: DataDictionary,
    backend: Optional[object],
    table_name: str,
    field_names: List[str],
    editors: Dict[str, QWidget],
    lang: LanguageCode,
) -> None:
    """為有 SEARCH_RET 的輸入欄安裝 editingFinished／焦點離開時回寫。"""
    for field in field_names:
        if not _form_field_has_search_ret(data_dict, table_name, field):
            continue
        ed = editors.get(field)
        if isinstance(ed, QComboBox):
            if getattr(ed, "_wolee_search_ret_hooked", False):
                continue
            ed._wolee_search_ret_hooked = True  # type: ignore[attr-defined]

            def _on_combo_finished(_idx: int = -1, f=field) -> None:
                apply_form_field_search_ret(
                    host=host,
                    data_dict=data_dict,
                    backend=backend,
                    table_name=table_name,
                    field=f,
                    editors=editors,
                    lang=lang,
                )

            ed.activated.connect(_on_combo_finished)
            le = ed.lineEdit()
            if le is not None:
                le.editingFinished.connect(_on_combo_finished)
            continue
        if not isinstance(ed, QLineEdit):
            continue
        if getattr(ed, "_wolee_search_ret_hooked", False):
            continue
        ed._wolee_search_ret_hooked = True  # type: ignore[attr-defined]

        def _on_finished(_checked=False, f=field) -> None:
            apply_form_field_search_ret(
                host=host,
                data_dict=data_dict,
                backend=backend,
                table_name=table_name,
                field=f,
                editors=editors,
                lang=lang,
            )

        ed.editingFinished.connect(_on_finished)


class SimpleTableModel(QAbstractTableModel):
    """
    簡單資料模型：rows 為資料庫完整列；column_source_indices 將 Grid 欄對應到實體欄索引。
    editable=True 時儲存格可編輯，寫回對應實體欄（與 WorkPage Grid 同一套顯示規則）。
    enable_row_drag=True 時可於把手欄拖曳換列；改 ITEM_NO 也會移到對應列並重算項數。
    """

    _ROW_MIME = "application/x-wolee-tx-row"
    _HANDLE_FIELD = "__ROW_HANDLE__"

    def __init__(
        self,
        headers: List[str],
        rows: List[List[str]],
        parent=None,
        column_source_indices: Optional[List[int]] = None,
        display_fields: Optional[List[str]] = None,
        display_formats: Optional[List[str]] = None,
        data_dict: Optional[DataDictionary] = None,
        table_name: str = "",
        editable: bool = False,
        physical_column_count: Optional[int] = None,
        min_display_rows: int = 0,
        *,
        enable_row_drag: bool = False,
        physical_fields: Optional[List[str]] = None,
        on_rows_reordered: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._headers = headers
        self._rows = rows
        self._min_display_rows = max(0, int(min_display_rows))
        n = len(headers)
        self._col_src: Optional[List[int]] = (
            list(column_source_indices) if column_source_indices is not None else None
        )
        if self._col_src is not None and len(self._col_src) != n:
            self._col_src = list(range(n))
        self._display_fields = list(display_fields or [])
        self._display_formats = list(display_formats or [])
        self._data_dict = data_dict
        self._table_name = (table_name or "").strip()
        self._editable = bool(editable)
        self._enable_row_drag = bool(enable_row_drag)
        self._physical_fields = list(physical_fields or [])
        self._on_rows_reordered = on_rows_reordered
        if physical_column_count is not None:
            self._n_phys = max(1, int(physical_column_count))
        elif self._col_src:
            self._n_phys = max(self._col_src) + 1
        else:
            self._n_phys = max(len(self._headers), 1)

    def data_row_count(self) -> int:
        return len(self._rows)

    def _is_padding_row(self, row: int) -> bool:
        return row >= self.data_row_count()

    def _field_meta_at_column(self, col: int) -> tuple[str, str, str]:
        f_name = (
            self._display_fields[col] if col < len(self._display_fields) else ""
        )
        f_fmt = ""
        f_typ = ""
        if self._data_dict and self._table_name and f_name:
            f_fmt = self._data_dict.get_data_format(self._table_name, f_name)
            f_typ = self._data_dict.get_data_type(self._table_name, f_name)
        if not f_fmt and col < len(self._display_formats):
            f_fmt = self._display_formats[col]
        return f_name, f_fmt, f_typ

    def _is_item_no_column(self, col: int) -> bool:
        f_name, _, _ = self._field_meta_at_column(col)
        return (f_name or "").strip().upper() == "ITEM_NO"

    def is_row_handle_column(self, col: int) -> bool:
        if not self._enable_row_drag or col < 0:
            return False
        if self._display_fields and col < len(self._display_fields):
            return self._display_fields[col] == self._HANDLE_FIELD
        if self._col_src and col < len(self._col_src):
            return self._col_src[col] < 0
        return False

    def _renumber_and_notify(self, select_row: int) -> None:
        if self._physical_fields:
            renumber_item_no(self._physical_fields, self._rows)
        self.layoutChanged.emit()
        if self._on_rows_reordered is not None:
            self._on_rows_reordered(select_row)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return max(self.data_row_count(), self._min_display_rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        return len(self._headers)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if self._is_padding_row(index.row()):
            return Qt.ItemFlag.ItemIsEnabled
        if self.is_row_handle_column(index.column()):
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        f = super().flags(index)
        if self._editable:
            f |= Qt.ItemFlag.ItemIsEditable
        return f

    def supportedDropActions(self) -> Qt.DropAction:  # type: ignore[override]
        if self._enable_row_drag:
            return Qt.DropAction.MoveAction
        return super().supportedDropActions()

    def mimeTypes(self) -> List[str]:  # type: ignore[override]
        if self._enable_row_drag:
            return [self._ROW_MIME]
        return super().mimeTypes()

    def mimeData(self, indexes: List[QModelIndex]) -> Optional[QMimeData]:  # type: ignore[override]
        if not self._enable_row_drag:
            return super().mimeData(indexes)
        rows = sorted(
            {
                idx.row()
                for idx in indexes
                if idx.isValid() and not self._is_padding_row(idx.row())
            }
        )
        if not rows:
            return None
        mime = QMimeData()
        # 目前只移動目前選取的第一列（單列拖曳）
        mime.setData(self._ROW_MIME, QByteArray(str(rows[0]).encode("utf-8")))
        return mime

    def dropMimeData(  # type: ignore[override]
        self,
        data: Optional[QMimeData],
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex,
    ) -> bool:
        if not self._enable_row_drag or action != Qt.DropAction.MoveAction:
            return False
        if data is None or not data.hasFormat(self._ROW_MIME):
            return False
        try:
            src = int(bytes(data.data(self._ROW_MIME)).decode("utf-8"))
        except Exception:
            return False
        n = self.data_row_count()
        if src < 0 or src >= n:
            return False
        if row < 0:
            dest_before = parent.row() if parent.isValid() else n
            if dest_before < 0:
                dest_before = n
        else:
            dest_before = row
        new_idx = move_row(self._rows, src, dest_before)
        if new_idx == src and dest_before in (src, src + 1):
            return False
        self._renumber_and_notify(new_idx)
        return True

    def canDropMimeData(  # type: ignore[override]
        self,
        data: Optional[QMimeData],
        action: Qt.DropAction,
        row: int,
        column: int,
        parent: QModelIndex,
    ) -> bool:
        if not self._enable_row_drag:
            return False
        return bool(
            data is not None
            and data.hasFormat(self._ROW_MIME)
            and action == Qt.DropAction.MoveAction
        )

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if self.is_row_handle_column(col):
            if self._is_padding_row(row):
                return "" if role in (
                    Qt.ItemDataRole.DisplayRole,
                    Qt.ItemDataRole.EditRole,
                ) else None
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return "⋮"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if role == Qt.ItemDataRole.ToolTipRole:
                return "拖曳移動列"
            if role == Qt.ItemDataRole.FontRole:
                return _grid_cell_font()
            return None
        if self._is_padding_row(row):
            if role in (
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.EditRole,
            ):
                return ""
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if role == Qt.ItemDataRole.FontRole:
                return _grid_cell_font(_font_base_dir_for(None))
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            try:
                phys = col if self._col_src is None else self._col_src[col]
                if phys < 0:
                    return ""
                r = self._rows[row]
                raw = r[phys] if phys < len(r) else ""
                f_name, f_fmt, f_typ = self._field_meta_at_column(col)
                if role == Qt.ItemDataRole.EditRole and (
                    is_numeric_data_type(f_typ) or is_boolean_data_type(f_typ)
                ):
                    return (raw or "").strip()
                return format_cell_display(f_name, raw, f_fmt, f_typ)
            except Exception:
                return ""
        if role == Qt.ItemDataRole.TextAlignmentRole:
            try:
                f_name, f_fmt, f_typ = self._field_meta_at_column(col)
                return _grid_column_text_alignment(f_name, f_fmt, f_typ)
            except Exception:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.FontRole:
            return _grid_cell_font()
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:  # type: ignore[override]
        if not self._editable or role != Qt.ItemDataRole.EditRole:
            return False
        if not index.isValid():
            return False
        if self.is_row_handle_column(index.column()):
            return False
        row, col = index.row(), index.column()
        if row < 0 or row >= len(self._rows):
            return False
        phys = col if self._col_src is None else self._col_src[col]
        if phys < 0:
            return False
        r = self._rows[row]
        while len(r) < self._n_phys:
            r.append("")
        while len(r) <= phys:
            r.append("")
        raw_in = str(value).strip() if value is not None else ""
        f_name, f_fmt, f_typ = self._field_meta_at_column(col)
        # 編輯 ITEM_NO：移到目標列後自動重算全部項數
        if (f_name or "").strip().upper() == "ITEM_NO" and raw_in:
            try:
                target_1 = int(float(raw_in))
            except (TypeError, ValueError):
                target_1 = row + 1
            new_idx = relocate_row(self._rows, row, target_1 - 1)
            self._renumber_and_notify(new_idx)
            return True
        r[phys] = normalize_storage_value(f_name, f_fmt, raw_in, f_typ)
        self.dataChanged.emit(
            index,
            index,
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole],
        )
        return True

    def set_display_headers(self, headers: List[str]) -> None:
        if len(headers) != len(self._headers):
            return
        self._headers = list(headers)
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            0,
            max(0, len(self._headers) - 1),
        )

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole  # type: ignore[override]
    ):
        if orientation == Qt.Orientation.Vertical:
            return super().headerData(section, orientation, role)
        if not (0 <= section < len(self._headers)):
            return super().headerData(section, orientation, role)
        if self.is_row_handle_column(section):
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter)
            if role == Qt.ItemDataRole.ToolTipRole:
                return "拖曳移動列"
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._headers[section]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            f_name, f_fmt, f_typ = self._field_meta_at_column(section)
            return _grid_column_text_alignment(f_name, f_fmt, f_typ)
        return super().headerData(section, orientation, role)


def grid_model_data_row_count(model) -> int:
    """實際資料列數（不含為填滿可視高度而補的空白列）。"""
    if model is None:
        return 0
    fn = getattr(model, "data_row_count", None)
    if callable(fn):
        return int(fn())
    return model.rowCount()


def _grid_data_row_count(view: QAbstractItemView) -> int:
    """Grid 實際資料列數（不含 padding 列）。"""
    return grid_model_data_row_count(view.model())


def format_record_nav_label(total: int, current_1based: Optional[int]) -> str:
    if total <= 0:
        return "0/0"
    if current_1based is None:
        return f"-/{total}"
    return f"{current_1based}/{total}"


def _grid_table_outer_height(tv: QTableView, visible_rows: int) -> int:
    """表格外框高度：viewport 可完整顯示 visible_rows 列（含格線、表頭、邊框）。"""
    bd = _font_base_dir_for(tv)
    row_h = _grid_row_height_px(bd)
    vh = tv.verticalHeader()
    vh.setDefaultSectionSize(row_h)
    vh.setMinimumSectionSize(row_h)
    vh.setMaximumSectionSize(row_h)
    # TX 明細：左側保留窄空位方便選列／拖曳；其餘 Grid 仍隱藏列號
    if not bool(tv.property("txRowSelectGutter")):
        vh.setVisible(False)

    hdr = tv.horizontalHeader()
    fm_hdr = QFontMetrics(hdr.font())
    # 與 main_window QHeaderView::section（padding 4px、邊框）對齊，避免低估表頭高度
    header_h = max(hdr.sizeHint().height(), fm_hdr.height() + 12)

    grid_lines = max(0, visible_rows - 1) if tv.showGrid() else 0
    frame = 2 * max(1, tv.frameWidth())
    viewport_h = row_h * visible_rows + grid_lines
    return viewport_h + header_h + frame + 4


def apply_grid_visible_row_count(tv: QTableView, visible_rows: int) -> None:
    """依可視列數重算表格外框高度（setModel 後可再呼叫一次）。"""
    row_h = _grid_row_height_px(_font_base_dir_for(tv))
    grid_lines = max(0, visible_rows - 1) if tv.showGrid() else 0
    need_viewport_h = row_h * visible_rows + grid_lines

    def _apply_height(extra: int = 0) -> None:
        desired_h = _grid_table_outer_height(tv, visible_rows) + extra
        tv.setMinimumHeight(desired_h)
        tv.setMaximumHeight(desired_h)

    def _fine_tune_after_layout() -> None:
        vp_h = tv.viewport().height()
        if vp_h <= 0 or vp_h >= need_viewport_h:
            return
        _apply_height(need_viewport_h - vp_h)

    _apply_height()
    QTimer.singleShot(0, _fine_tune_after_layout)


def configure_grid_table_view(
    tv: QTableView, visible_rows: int, base_dir: Optional[str] = None
) -> None:
    """
    列高約 26px；表格外框高度固定為 visible_rows 列可視區（有捲軸時仍顯示相同列數）。
    資料列數可少於可視列數，不足部分為 viewport 空白區間（勿用 min_display_rows 補列）。
    """
    tv.setObjectName("appGridTable")
    tv.setStyleSheet(
        "#appGridTable::item { padding-top: 0px; padding-bottom: 0px; padding-left: 6px; padding-right: 6px; }"
    )
    tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tv.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    tv.setAlternatingRowColors(True)
    tv.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tv.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tv.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
    f_cell = QFont(tv.font())
    f_cell.setPointSize(_grid_cell_pt(base_dir))
    f_cell.setWeight(QFont.Weight.Normal)
    tv.setFont(f_cell)
    hdr = tv.horizontalHeader()
    f_hdr = QFont(hdr.font())
    f_hdr.setPointSize(_grid_header_pt(base_dir))
    f_hdr.setWeight(QFont.Weight.Bold)
    hdr.setFont(f_hdr)
    hdr.setStretchLastSection(False)
    _ensure_grid_cell_delegate(tv, base_dir)
    apply_grid_visible_row_count(tv, visible_rows)
    tv.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def _tsv_cell_text(value: object) -> str:
    return str(value if value is not None else "").replace("\t", " ").replace("\r", " ").replace("\n", " ")


def copy_item_view_rows_to_clipboard(
    view: QAbstractItemView,
    rows: Optional[List[int]] = None,
    *,
    include_headers: bool = True,
) -> bool:
    """將 Grid 選取列（或指定列）以 Tab 分隔複製到剪貼簿（含表頭）。"""
    model = view.model()
    if model is None:
        return False
    sm = view.selectionModel()
    if rows is None:
        if sm is None or not sm.hasSelection():
            return False
        rows = sorted({idx.row() for idx in sm.selectedIndexes()})
    if not rows:
        return False
    ncols = model.columnCount()
    lines: List[str] = []
    if include_headers:
        hdrs = []
        for c in range(ncols):
            h = model.headerData(c, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            hdrs.append(_tsv_cell_text(h))
        lines.append("\t".join(hdrs))
    for r in rows:
        if r < 0 or r >= model.rowCount():
            continue
        cells = []
        for c in range(ncols):
            idx = model.index(r, c)
            val = model.data(idx, Qt.ItemDataRole.DisplayRole) if idx.isValid() else ""
            cells.append(_tsv_cell_text(val))
        lines.append("\t".join(cells))
    QGuiApplication.clipboard().setText("\n".join(lines))
    return True


def install_grid_copy_context_menu(
    view: QAbstractItemView,
    lang_resolver: Callable[[], LanguageCode],
) -> None:
    """Grid 右鍵選單：複製所選、複製全部、全選。"""
    if getattr(view, "_wolee_copy_menu_installed", False):
        return
    view._wolee_copy_menu_installed = True
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _on_menu(pos) -> None:
        model = view.model()
        if model is None:
            return
        idx = view.indexAt(pos)
        sm = view.selectionModel()
        if idx.isValid() and sm is not None:
            if not sm.isRowSelected(idx.row(), idx.parent()):
                view.selectRow(idx.row())
        lang = lang_resolver()
        chn = lang == "CHN"
        nrows = grid_model_data_row_count(model)
        sel_rows = sorted({i.row() for i in sm.selectedIndexes()}) if sm else []
        menu = QMenu(view)
        lbl_copy = "複製到剪貼簿" if chn else "Copy to Clipboard"
        lbl_copy_all = "複製全部到剪貼簿" if chn else "Copy All to Clipboard"
        lbl_sel_all = "全選" if chn else "Select All"
        act_copy = menu.addAction(
            f"{lbl_copy} ({len(sel_rows)})" if sel_rows else lbl_copy
        )
        act_copy.setEnabled(bool(sel_rows))
        act_copy_all = menu.addAction(lbl_copy_all)
        act_copy_all.setEnabled(nrows > 0)
        act_sel_all = menu.addAction(lbl_sel_all)
        act_sel_all.setEnabled(nrows > 0)
        chosen = menu.exec(view.mapToGlobal(pos))
        if chosen is act_copy:
            copy_item_view_rows_to_clipboard(view, sel_rows)
        elif chosen is act_copy_all:
            all_rows = list(range(nrows))
            if not hasattr(model, "data_row_count"):
                all_rows = []
                for r in range(model.rowCount()):
                    has_data = False
                    for c in range(model.columnCount()):
                        midx = model.index(r, c)
                        if midx.isValid() and str(
                            model.data(midx, Qt.ItemDataRole.DisplayRole) or ""
                        ).strip():
                            has_data = True
                            break
                    if has_data:
                        all_rows.append(r)
            copy_item_view_rows_to_clipboard(view, all_rows)
        elif chosen is act_sel_all:
            view.selectAll()

    view.customContextMenuRequested.connect(_on_menu)


def _grid_char_unit_px(fm_cell: QFontMetrics) -> int:
    """欄寬上下限用的『字元』參考寬度（中英數）。"""
    return max(
        1,
        fm_cell.horizontalAdvance("0"),
        fm_cell.horizontalAdvance("國"),
        fm_cell.horizontalAdvance("W"),
    )


def _grid_section_width_px(
    wdict: int,
    hdr_text: str,
    cell_texts: List[str],
    fm_cell: QFontMetrics,
    fm_hdr: QFontMetrics,
) -> int:
    """單欄寬度：有 WIDTH 時依字元數，否則依表頭與儲存格內容量測。"""
    ch = _grid_char_unit_px(fm_cell)
    min_px = ch * _GRID_CHAR_MIN + _GRID_COL_PAD_PX
    max_px = ch * _GRID_CHAR_MAX + _GRID_COL_PAD_PX
    w_hdr = fm_hdr.horizontalAdvance(hdr_text) + _GRID_COL_PAD_PX
    max_cell = 0
    for s in cell_texts:
        max_cell = max(max_cell, fm_cell.horizontalAdvance(s))
    max_cell += 16
    if wdict > 0:
        wpx = ch * int(wdict) + _GRID_COL_PAD_PX
        return max(wpx, w_hdr)
    return max(min_px, min(max_px, max(w_hdr, max_cell)))


def _apply_grid_header_fonts(
    tv: QTableView, base_dir: Optional[str] = None
) -> tuple[QFontMetrics, QFontMetrics]:
    hdr_w = tv.horizontalHeader()
    f_cell = QFont(tv.font())
    f_cell.setPointSize(_grid_cell_pt(base_dir))
    f_cell.setWeight(QFont.Weight.Normal)
    tv.setFont(f_cell)
    f_hdr = QFont(hdr_w.font())
    f_hdr.setPointSize(_grid_header_pt(base_dir))
    f_hdr.setWeight(QFont.Weight.Bold)
    hdr_w.setFont(f_hdr)
    hdr_w.setStretchLastSection(False)
    tv.verticalHeader().setDefaultSectionSize(_grid_row_height_px(base_dir))
    fm_hdr = QFontMetrics(f_hdr)
    header_h = max(hdr_w.sizeHint().height(), fm_hdr.height() + 12)
    hdr_w.setFixedHeight(header_h)
    return QFontMetrics(f_cell), QFontMetrics(f_hdr)


def apply_qtablewidget_column_widths(
    tw: QTableWidget,
    table_name: str,
    field_names: List[str],
    data_dict: Optional[DataDictionary],
    max_scan_rows: Optional[int] = None,
) -> None:
    """QTableWidget 初始欄寬（含 columns.WIDTH）；表頭為 Interactive，使用者可拖曳調整。"""
    hdr = tw.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    fm_cell, fm_hdr = _apply_grid_header_fonts_for_widget(tw)
    ncols = tw.columnCount()
    nrows_all = tw.rowCount()
    if max_scan_rows is None:
        nrows = min(max(0, nrows_all), _GRID_MAX_SCAN_ROWS)
    elif max_scan_rows <= 0:
        nrows = max(0, nrows_all)
    else:
        nrows = min(max(0, nrows_all), max_scan_rows)
    for col in range(ncols):
        hi = tw.horizontalHeaderItem(col)
        hdr_t = hi.text() if hi is not None else ""
        texts: List[str] = []
        for r in range(nrows):
            it = tw.item(r, col)
            texts.append(it.text() if it is not None else "")
        fn = field_names[col] if col < len(field_names) else ""
        wdict = 0
        if data_dict and table_name and fn:
            wdict = data_dict.get_grid_width_chars(table_name, fn)
        col_w = _grid_section_width_px(wdict, hdr_t, texts, fm_cell, fm_hdr)
        hdr.resizeSection(col, col_w)


def _apply_grid_header_fonts_for_widget(
    tw: QTableWidget, base_dir: Optional[str] = None
) -> tuple[QFontMetrics, QFontMetrics]:
    bd = base_dir or _font_base_dir_for(tw)
    hdr = tw.horizontalHeader()
    f_cell = QFont(tw.font())
    f_cell.setPointSize(_grid_cell_pt(bd))
    f_cell.setWeight(QFont.Weight.Normal)
    tw.setFont(f_cell)
    f_hdr = QFont(hdr.font())
    f_hdr.setPointSize(_grid_header_pt(bd))
    f_hdr.setWeight(QFont.Weight.Bold)
    hdr.setFont(f_hdr)
    hdr.setStretchLastSection(False)
    tw.verticalHeader().setDefaultSectionSize(_grid_row_height_px(bd))
    return QFontMetrics(f_cell), QFontMetrics(f_hdr)


def apply_grid_column_width_limits(
    tv: QTableView, max_scan_rows: Optional[int] = None
) -> None:
    """
    設定 Grid 初始欄寬（10pt 儲存格、11pt 表頭）；表頭為 Interactive，使用者可拖曳調整。
    - columns.WIDTH > 0：以 WIDTH 字元數為準（表頭較寬時略放大以免截斷）。
    - 未設定 WIDTH：掃描列量測內容，至少約 6 字元、至多約 80 字元寬。
    """
    m = tv.model()
    if m is None:
        return
    hdr_w = tv.horizontalHeader()
    hdr_w.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    fm_cell, fm_hdr = _apply_grid_header_fonts(tv, _font_base_dir_for(tv))

    ncols = m.columnCount()
    nrows_all = m.rowCount()
    if max_scan_rows is None:
        nrows = min(max(0, nrows_all), _GRID_MAX_SCAN_ROWS)
    elif max_scan_rows <= 0:
        nrows = max(0, nrows_all)
    else:
        nrows = min(max(0, nrows_all), max_scan_rows)

    for col in range(ncols):
        try:
            hv = m.headerData(
                col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
            )
            hdr_t = str(hv) if hv is not None else ""
        except Exception:
            hdr_t = ""
        texts: List[str] = []
        for r in range(nrows):
            try:
                idx = m.index(r, col)
                t = m.data(idx, Qt.ItemDataRole.DisplayRole)
                texts.append(str(t) if t is not None else "")
            except Exception:
                texts.append("")

        wdict = 0
        if isinstance(m, SimpleTableModel) and m._data_dict and m._table_name:
            fn, _, _ = m._field_meta_at_column(col)
            if fn:
                wdict = m._data_dict.get_grid_width_chars(m._table_name, fn)

        col_w = _grid_section_width_px(wdict, hdr_t, texts, fm_cell, fm_hdr)
        hdr_w.resizeSection(col, col_w)


def bind_grid_nav_icon_buttons(
    lang: LanguageCode,
    style: QStyle,
    btn_first: QPushButton,
    btn_prev: QPushButton,
    btn_next: QPushButton,
    btn_last: QPushButton,
) -> None:
    btn_first.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
    btn_prev.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
    btn_next.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
    btn_last.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
    for b in (btn_first, btn_prev, btn_next, btn_last):
        b.setText("")
    if lang == "CHN":
        btn_first.setToolTip("首筆")
        btn_prev.setToolTip("上筆")
        btn_next.setToolTip("下筆")
        btn_last.setToolTip("末筆")
    else:
        btn_first.setToolTip("First")
        btn_prev.setToolTip("Previous")
        btn_next.setToolTip("Next")
        btn_last.setToolTip("Last")


def _qt_obj_alive(obj: object) -> bool:
    """PyQt wrapper 對應的 C++ 物件是否仍存在。"""
    if obj is None:
        return False
    try:
        from PyQt6 import sip

        return not sip.isdeleted(obj)  # type: ignore[arg-type]
    except Exception:
        try:
            getattr(obj, "objectName")
            return True
        except RuntimeError:
            return False


class _TxHandleColDragFilter(QObject):
    """在 TX 明細第一欄（⋮ 把手）按住拖曳以移動列。"""

    def __init__(self, pane: "TxDetailGridPane") -> None:
        super().__init__(pane)
        self._pane = pane
        self._src_row = -1
        self._press_y = 0
        self._dragging = False
        self._grabbed = False

    def _table(self):
        pane = getattr(self, "_pane", None)
        if not _qt_obj_alive(pane):
            return None
        table = getattr(pane, "table", None)
        if not _qt_obj_alive(table):
            return None
        return table

    def _reset(self) -> None:
        table = self._table()
        if table is not None and self._grabbed:
            try:
                vp = table.viewport()
                if _qt_obj_alive(vp):
                    vp.releaseMouse()
            except RuntimeError:
                pass
        self._src_row = -1
        self._press_y = 0
        self._dragging = False
        self._grabbed = False

    def _row_at_viewport_y(self, y: int) -> int:
        table = self._table()
        pane = getattr(self, "_pane", None)
        if table is None or not _qt_obj_alive(pane):
            return -1
        n = len(getattr(pane, "_full_rows", []) or [])
        if n <= 0:
            return -1
        from PyQt6.QtCore import QPoint

        try:
            idx = table.indexAt(QPoint(8, int(y)))
            if idx.isValid() and 0 <= idx.row() < n:
                return idx.row()
            vp = table.viewport()
            if not _qt_obj_alive(vp):
                return -1
            if y < 0:
                return 0
            if y >= vp.height():
                return n - 1
            for dy in (0, -8, 8, -16, 16):
                idx2 = table.indexAt(QPoint(8, int(y) + dy))
                if idx2.isValid() and 0 <= idx2.row() < n:
                    return idx2.row()
        except RuntimeError:
            return -1
        return -1

    def eventFilter(self, obj, event):  # type: ignore[override]
        try:
            return self._event_filter_impl(obj, event)
        except RuntimeError:
            self._reset()
            return False

    def _event_filter_impl(self, obj, event) -> bool:
        table = self._table()
        if table is None:
            return False
        try:
            vp = table.viewport()
        except RuntimeError:
            return False
        if not _qt_obj_alive(vp) or obj is not vp:
            return False
        model = table.model()
        if not isinstance(model, SimpleTableModel) or not model._enable_row_drag:
            return False
        et = event.type()

        if et == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            idx = table.indexAt(event.position().toPoint())
            if not idx.isValid() or not model.is_row_handle_column(idx.column()):
                return False
            rows = getattr(self._pane, "_full_rows", []) or []
            if idx.row() < 0 or idx.row() >= len(rows):
                return False
            self._src_row = idx.row()
            self._press_y = int(event.position().y())
            self._dragging = False
            self._grabbed = True
            vp.grabMouse()
            self._pane._nav_select_row(self._src_row)
            return True

        if et == QEvent.Type.MouseMove:
            if self._src_row < 0 or not self._grabbed:
                return False
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return False
            y = int(event.position().y())
            if not self._dragging and abs(y - self._press_y) >= 3:
                self._dragging = True
            if self._dragging:
                dest = self._row_at_viewport_y(y)
                if dest >= 0:
                    table.selectRow(dest)
            return True

        if et == QEvent.Type.MouseButtonRelease:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            if self._src_row < 0 or not self._grabbed:
                return False
            src = self._src_row
            dragging = self._dragging
            dest = self._row_at_viewport_y(int(event.position().y()))
            self._reset()
            pane = self._pane
            if not _qt_obj_alive(pane):
                return True
            if dragging and dest >= 0 and dest != src:
                pane._relocate_row_by_index(src, dest)
            else:
                pane._nav_select_row(src)
            return True

        return False


class TxDetailGridPane(QWidget):
    """
    交易明細／輸入用 Grid：搜尋列左側為新增／更改／刪除／複製（QStyle 標準圖示 + 漸層按鈕），
    右側為搜尋；下方 QTableView、導覽列。無過濾。
    儲存格一律可編輯（含已綁定 TX_KEY 的明細）；新增列時若主檔有 TX_KEY 會自動帶入該欄。
    可視區固定 _FIXED_VIEW_ROWS（6）列高度；資料不足 6 筆時僅顯示實際列，其下為空白區間（不補模型空白列）。
    超過 6 筆時垂直捲動，可視區仍為 6 列。不顯示列號。
    """

    _FIXED_VIEW_ROWS = 6
    _FETCH_LIMIT = 500

    def __init__(
        self,
        tx_name: str,
        data_dict: DataDictionary,
        lang: LanguageCode,
        backend: Optional["DbBackendBase"],
        master_tx_key: Optional[str],
        master_filter_column: Optional[str] = None,
        source_tx_key: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.tx_name = tx_name
        self.data_dict = data_dict
        self.lang = lang
        self.backend = backend
        self._master_tx_key = master_tx_key
        self._source_tx_key = (source_tx_key or "").strip() or None
        self._master_filter_column = (master_filter_column or "").strip().upper() or None
        self._phys: List[str] = []
        self._cols: List[str] = []
        self._src_idx: List[int] = []
        self._full_rows: List[List[str]] = []
        self.last_error: str = ""
        self._build_ui()
        self.reload_from_backend()

    def _rows_for_save(self, key_col: Optional[str], key_value: Optional[str]) -> List[List[str]]:
        rows: List[List[str]] = []
        key_idx = None
        if key_col:
            for i, c in enumerate(self._phys):
                if c.strip().upper() == key_col.strip().upper():
                    key_idx = i
                    break
        for src in self._full_rows:
            row = list(src[: len(self._phys)])
            while len(row) < len(self._phys):
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
                rows.append(row)
        return rows

    def save_to_backend(self) -> bool:
        """
        將目前 TX Grid 內容寫回資料庫。
        規則：若有主檔鍵值，先刪除既有同鍵資料再整批重寫。
        """
        self.last_error = ""
        if self.backend is None:
            return True
        if not self._phys:
            self.last_error = f"{self.tx_name}: missing physical columns."
            return False

        key_col = self._resolve_filter_column(self._phys)
        if self._master_tx_key and not key_col:
            self.last_error = f"{self.tx_name}: key column not found for filtered save."
            return False

        key_value = self._master_tx_key
        if key_col and key_value is not None:
            key_fmt = self.data_dict.get_data_format(self.tx_name, key_col)
            key_typ = self.data_dict.get_data_type(self.tx_name, key_col)
            key_value = normalize_storage_value(key_col, key_fmt, key_value, key_typ)

        if key_value and key_col:
            existing = self.backend.fetch_rows_where(
                self.tx_name,
                key_col,
                key_value,
                limit=self._FETCH_LIMIT,
                column_order=self._phys,
            )
            if existing:
                # 刪舊明細只用鍵欄位，避免整列值比對（型別/空白差異）導致刪除失敗。
                if not self.backend.delete_one(
                    self.tx_name,
                    [key_col],
                    [key_value],
                ):
                    be = str(getattr(self.backend, "last_error", "") or "").strip()
                    self.last_error = be or f"{self.tx_name}: failed deleting old tx rows by key."
                    return False

        self._renumber_item_nos()
        rows = self._rows_for_save(key_col, key_value)
        auto_like = {"ID", "AUTOID", "AUTO_ID", "RECNO", "REC_NO"}
        string_types = {"S", "STRING", "STR", "TEXT", "CHAR", "VARCHAR", "NVARCHAR"}
        for row in rows:
            insert_fields: List[str] = []
            insert_values: List[str] = []
            for i, col in enumerate(self._phys):
                col_up = col.strip().upper()
                if key_col and col_up == key_col.strip().upper() and key_value is not None:
                    insert_fields.append(col)
                    insert_values.append(key_value)
                    continue

                # 常見自動編號欄位不主動插入，避免 Access 拒絕。
                if col_up in auto_like:
                    continue

                raw = row[i] if i < len(row) else ""
                txt = str(raw).strip()
                if txt == "":
                    dtyp = self.data_dict.get_data_type(self.tx_name, col).strip().upper()
                    # 非字串空值不插入，交由 DB 預設/Null 處理，避免型別衝突。
                    if dtyp not in string_types:
                        continue
                fmt = self.data_dict.get_data_format(self.tx_name, col)
                dtyp = self.data_dict.get_data_type(self.tx_name, col)
                norm = normalize_storage_value(col, fmt, str(raw), dtyp)
                insert_fields.append(col)
                insert_values.append(norm)

            if not insert_fields:
                continue
            if not self.backend.insert_one(self.tx_name, insert_fields, insert_values):
                be = str(getattr(self.backend, "last_error", "") or "").strip()
                preview = ", ".join(f"{f}={v}" for f, v in zip(insert_fields[:6], insert_values[:6]))
                self.last_error = be or f"{self.tx_name}: failed inserting tx row. [{preview}]"
                return False
        return True

    def _resolve_filter_column(self, physical_fields: List[str]) -> Optional[str]:
        if self._master_filter_column:
            for c in physical_fields:
                if c.strip().upper() == self._master_filter_column:
                    return c
        for c in physical_fields:
            if c.strip().upper() == "TX_KEY":
                return c
        return None

    def focusInEvent(self, event) -> None:  # type: ignore[override]
        if hasattr(self, "txt_search") and self.txt_search is not None:
            self.txt_search.setFocus()
        super().focusInEvent(event)

    def _search_label_text(self) -> str:
        return "搜尋:" if self.lang == "CHN" else "Search:"

    def _apply_tx_crud_button_texts_and_icons(self, st: QStyle) -> None:
        self.btn_tx_add.setIcon(icon_from_key(st, "add"))
        self.btn_tx_edit.setIcon(icon_from_key(st, "edit"))
        self.btn_tx_delete.setIcon(icon_from_key(st, "delete"))
        self.btn_tx_copy.setIcon(icon_from_key(st, "copy"))
        self.btn_tx_up.setIcon(
            st.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        )
        self.btn_tx_down.setIcon(
            st.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        )
        if self.lang == "CHN":
            self.btn_tx_add.setText("新增")
            self.btn_tx_edit.setText("更改")
            self.btn_tx_delete.setText("刪除")
            self.btn_tx_copy.setText("複製")
            self.btn_tx_up.setText("上移")
            self.btn_tx_down.setText("下移")
        else:
            self.btn_tx_add.setText("Add")
            self.btn_tx_edit.setText("Edit")
            self.btn_tx_delete.setText("Delete")
            self.btn_tx_copy.setText("Copy")
            self.btn_tx_up.setText("Up")
            self.btn_tx_down.setText("Down")
        for b in (
            self.btn_tx_add,
            self.btn_tx_edit,
            self.btn_tx_delete,
            self.btn_tx_copy,
            self.btn_tx_up,
            self.btn_tx_down,
        ):
            apply_work_action_button_style(b)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self.btn_nav_first = QPushButton()
        self.btn_nav_prev = QPushButton()
        self.btn_nav_next = QPushButton()
        self.btn_nav_last = QPushButton()
        for nb in (
            self.btn_nav_first,
            self.btn_nav_prev,
            self.btn_nav_next,
            self.btn_nav_last,
        ):
            apply_nav_button_style(nb)
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_nav_first,
            self.btn_nav_prev,
            self.btn_nav_next,
            self.btn_nav_last,
        )
        self.btn_nav_first.clicked.connect(self._on_nav_first)
        self.btn_nav_prev.clicked.connect(self._on_nav_prev)
        self.btn_nav_next.clicked.connect(self._on_nav_next)
        self.btn_nav_last.clicked.connect(self._on_nav_last)
        search_layout.addWidget(self.btn_nav_first)
        search_layout.addWidget(self.btn_nav_prev)
        search_layout.addWidget(self.btn_nav_next)
        search_layout.addWidget(self.btn_nav_last)
        self.lbl_record_nav = QLabel()
        self.lbl_record_nav.setStyleSheet(
            f"font-size: 11pt; font-weight: 700; color: {theme_surface_text_color()};"
        )
        search_layout.addWidget(self.lbl_record_nav)

        st = self.style()
        self.btn_tx_add = QPushButton()
        self.btn_tx_edit = QPushButton()
        self.btn_tx_delete = QPushButton()
        self.btn_tx_copy = QPushButton()
        self.btn_tx_up = QPushButton()
        self.btn_tx_down = QPushButton()
        self._apply_tx_crud_button_texts_and_icons(st)
        for b in (
            self.btn_tx_add,
            self.btn_tx_edit,
            self.btn_tx_delete,
            self.btn_tx_copy,
            self.btn_tx_up,
            self.btn_tx_down,
        ):
            apply_work_action_button_style(b)
        self.btn_tx_add.clicked.connect(self._on_tx_add_row)
        self.btn_tx_edit.clicked.connect(self._on_tx_edit_cell)
        self.btn_tx_delete.clicked.connect(self._on_tx_delete_row)
        self.btn_tx_copy.clicked.connect(self._on_tx_copy_row)
        self.btn_tx_up.clicked.connect(self._on_tx_move_up)
        self.btn_tx_down.clicked.connect(self._on_tx_move_down)
        search_layout.addWidget(self.btn_tx_add)
        search_layout.addWidget(self.btn_tx_edit)
        search_layout.addWidget(self.btn_tx_delete)
        search_layout.addWidget(self.btn_tx_copy)
        search_layout.addWidget(self.btn_tx_up)
        search_layout.addWidget(self.btn_tx_down)
        search_layout.addStretch(1)

        self.lbl_search = QLabel(self._search_label_text())
        self.lbl_search.setStyleSheet("font-size: 12pt; font-weight: 700;")
        self.txt_search = QLineEdit()
        _disable_ime(self.txt_search)
        self.txt_search.returnPressed.connect(self._on_tx_search_enter)
        search_layout.addWidget(self.lbl_search)
        search_layout.addWidget(self.txt_search, 1)
        self.btn_search = QPushButton()
        if self.lang == "CHN":
            self.btn_search.setText("搜尋")
        else:
            self.btn_search.setText("Search")
        self.btn_search.setIcon(icon_from_key(self.style(), "search"))
        apply_work_action_button_style(self.btn_search)
        self.btn_search.clicked.connect(self._on_tx_search_enter)
        search_layout.addWidget(self.btn_search)
        layout.addLayout(search_layout)

        self.table = QTableView()
        self.table.setObjectName("appGridTable")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(
            _grid_row_height_px(_font_base_dir_for(self))
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setDragEnabled(False)
        self.table.setAcceptDrops(False)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        _disable_ime(self.table)
        install_grid_copy_context_menu(self.table, lambda: self.lang)
        layout.addWidget(self.table)

    def set_language(self, lang: LanguageCode) -> None:
        self.lang = lang
        if hasattr(self, "lbl_search") and self.lbl_search:
            self.lbl_search.setText(self._search_label_text())
        if self.lang == "CHN":
            self.btn_search.setText("搜尋")
        else:
            self.btn_search.setText("Search")
        apply_work_action_button_style(self.btn_search)
        self._apply_tx_crud_button_texts_and_icons(self.style())
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_nav_first,
            self.btn_nav_prev,
            self.btn_nav_next,
            self.btn_nav_last,
        )
        self.update_headers_only()
        self._refresh_record_nav_ui()

    def _apply_row_handle_column(self) -> None:
        """第一欄為拖曳把手；隱藏垂直表頭。"""
        if not _qt_obj_alive(self.table):
            return
        self.table.verticalHeader().setVisible(False)
        model = self.table.model()
        if isinstance(model, SimpleTableModel) and model.columnCount() > 0:
            self.table.setColumnWidth(0, 22)
            hdr = self.table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        filt = getattr(self, "_handle_drag_filter", None)
        if filt is None:
            filt = _TxHandleColDragFilter(self)
            self._handle_drag_filter = filt
        try:
            vp = self.table.viewport()
            if _qt_obj_alive(vp):
                vp.removeEventFilter(filt)
                vp.installEventFilter(filt)
        except RuntimeError:
            return

    def _relocate_row_by_index(self, src: int, dest: int) -> None:
        """將明細列移到 dest（0-based），重算 ITEM_NO 並選取該列。"""
        if src < 0 or src >= len(self._full_rows):
            return
        new_idx = relocate_row(self._full_rows, src, dest)
        self._renumber_item_nos()
        self._apply_table_model(select_row=new_idx)

    def _make_model(self, row_lists: List[List[str]]) -> SimpleTableModel:
        titles = [
            self.data_dict.get_title(self.tx_name, c, self.lang) for c in self._cols
        ]
        headers = [""] + titles
        src_idx = [-1] + list(self._src_idx)
        display_fields = [SimpleTableModel._HANDLE_FIELD] + list(self._cols)
        return SimpleTableModel(
            headers,
            row_lists,
            self,
            src_idx,
            display_fields,
            [],
            self.data_dict,
            self.tx_name,
            editable=True,
            physical_column_count=len(self._phys),
            min_display_rows=0,
            enable_row_drag=True,
            physical_fields=self._phys,
            on_rows_reordered=self._on_tx_rows_reordered,
        )

    def _renumber_item_nos(self) -> None:
        renumber_item_no(self._phys, self._full_rows)

    def _on_tx_rows_reordered(self, new_row: int) -> None:
        self._nav_select_row(new_row)

    def _apply_table_model(self, select_row: Optional[int] = None) -> None:
        visible = self._full_rows
        configure_grid_table_view(
            self.table, self._FIXED_VIEW_ROWS, _font_base_dir_for(self)
        )
        self.table.verticalHeader().setVisible(False)
        model = self._make_model(visible)
        _end_grid_inplace_edit(self.table)
        self.table.setModel(model)
        apply_grid_column_width_limits(self.table)
        apply_grid_visible_row_count(self.table, self._FIXED_VIEW_ROWS)
        self._apply_row_handle_column()
        self._attach_grid_nav_selection()
        n = model.data_row_count()
        if n > 0:
            row = 0 if select_row is None else max(0, min(int(select_row), n - 1))
            focus_col = 1 if model.columnCount() > 1 else 0
            self.table.selectRow(row)
            self.table.setCurrentIndex(model.index(row, focus_col))
        self._refresh_record_nav_ui()

    def reload_from_backend(self) -> None:
        self.data_dict.load_columns_for_dbf(self.tx_name)
        phys: List[str] = []
        if self.backend is not None:
            phys = self.backend.list_columns(self.tx_name)
        if not phys:
            phys = ["LINE_NO", "ITEM_CODE", "QTY", "PRICE", "AMOUNT"]
        self._phys = phys
        cols, src_idx = self.data_dict.grid_display_projection(self.tx_name, phys)
        self._cols = cols
        self._src_idx = src_idx
        n_phys = len(phys)
        self._full_rows = []

        tx_key_col = self._resolve_filter_column(phys)

        if self.backend is not None:
            load_key = (self._master_tx_key or "").strip() or self._source_tx_key
            if load_key and tx_key_col:
                rows = self.backend.fetch_rows_where(
                    self.tx_name,
                    tx_key_col,
                    load_key,
                    limit=self._FETCH_LIMIT,
                    column_order=phys,
                )
            else:
                rows = []
            for rec in rows:
                row = list(rec)
                while len(row) < n_phys:
                    row.append("")
                self._full_rows.append(row[:n_phys])

            if self._source_tx_key and not (self._master_tx_key or "").strip():
                self._full_rows = _clear_tx_rows_master_keys(
                    self._full_rows,
                    phys,
                    key_column=tx_key_col or "",
                )

        self.txt_search.clear()
        self._apply_table_model()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)

    def update_headers_only(self) -> None:
        if not self._cols:
            return
        headers = [""] + [
            self.data_dict.get_title(self.tx_name, c, self.lang) for c in self._cols
        ]
        m = self.table.model()
        if isinstance(m, SimpleTableModel):
            m.set_display_headers(headers)
        apply_grid_column_width_limits(self.table)
        apply_grid_visible_row_count(self.table, self._FIXED_VIEW_ROWS)
        self._apply_row_handle_column()

    def refresh_data_cells(self) -> None:
        """資料字典重載後：重抓後端並重繪（與原 _setup_tx_grid 一致）。"""
        self.reload_from_backend()

    def reapply_theme_styles(self) -> None:
        for btn in (
            getattr(self, "btn_tx_add", None),
            getattr(self, "btn_tx_edit", None),
            getattr(self, "btn_tx_delete", None),
            getattr(self, "btn_tx_copy", None),
            getattr(self, "btn_tx_up", None),
            getattr(self, "btn_tx_down", None),
            getattr(self, "btn_search", None),
        ):
            if btn is not None:
                apply_work_action_button_style(btn)
        for nb in (
            getattr(self, "btn_nav_first", None),
            getattr(self, "btn_nav_prev", None),
            getattr(self, "btn_nav_next", None),
            getattr(self, "btn_nav_last", None),
        ):
            if nb is not None:
                apply_nav_button_style(nb)
        if hasattr(self, "lbl_record_nav") and self.lbl_record_nav is not None:
            self.lbl_record_nav.setStyleSheet(
                f"font-size: 11pt; font-weight: 700; color: {theme_surface_text_color()};"
            )
        reapply_grid_fonts(self.table, _font_base_dir_for(self))

    def _on_tx_search_enter(self) -> None:
        kw = self.txt_search.text().strip().lower()
        self._apply_table_model()
        m = self.table.model()
        if not kw or m is None:
            return
        for i, row in enumerate(self._full_rows):
            if any(kw in str(c).lower() for c in row):
                if i < grid_model_data_row_count(m):
                    focus_col = 1 if m.columnCount() > 1 else 0
                    idx = m.index(i, focus_col)
                    self.table.setCurrentIndex(idx)
                    self.table.selectRow(i)
                    self.table.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
                break
        self._refresh_record_nav_ui()

    def _refresh_record_nav_ui(self) -> None:
        m = self.table.model()
        total = grid_model_data_row_count(m)
        cur: Optional[int] = None
        idx = self.table.currentIndex()
        if idx.isValid() and m is not None and 0 <= idx.row() < total:
            cur = idx.row() + 1
        self.lbl_record_nav.setText(format_record_nav_label(total, cur))
        has_rows = total > 0
        row = idx.row() if idx.isValid() and m is not None else -1
        no_sel = not idx.isValid() or row < 0 or row >= total
        self.btn_nav_first.setEnabled(has_rows and (no_sel or row > 0))
        self.btn_nav_prev.setEnabled(has_rows and not no_sel and row > 0)
        self.btn_nav_next.setEnabled(has_rows and not no_sel and row < total - 1)
        self.btn_nav_last.setEnabled(has_rows and (no_sel or row < total - 1))
        self._refresh_tx_crud_buttons()

    def _refresh_tx_crud_buttons(self) -> None:
        m = self.table.model()
        n = grid_model_data_row_count(m)
        idx = self.table.currentIndex()
        row_ok = idx.isValid() and 0 <= idx.row() < n
        row = idx.row() if row_ok else -1
        self.btn_tx_add.setEnabled(bool(self._phys))
        self.btn_tx_edit.setEnabled(row_ok and n > 0)
        self.btn_tx_delete.setEnabled(row_ok and n > 0)
        self.btn_tx_copy.setEnabled(row_ok and n > 0)
        self.btn_tx_up.setEnabled(row_ok and row > 0)
        self.btn_tx_down.setEnabled(row_ok and row >= 0 and row < n - 1)

    def _attach_grid_nav_selection(self) -> None:
        sm = self.table.selectionModel()
        if sm is None:
            return
        try:
            sm.selectionChanged.disconnect(self._on_grid_selection_for_nav)
        except TypeError:
            pass
        sm.selectionChanged.connect(self._on_grid_selection_for_nav)

    def _on_grid_selection_for_nav(self, *_args) -> None:
        self._refresh_record_nav_ui()

    def _on_tx_add_row(self) -> None:
        if not self._phys:
            return
        n_phys = len(self._phys)
        new_row = [""] * n_phys
        if self._master_tx_key:
            key_col = self._resolve_filter_column(self._phys)
            for i, name in enumerate(self._phys):
                if key_col and name.strip().upper() == key_col.strip().upper():
                    new_row[i] = self._master_tx_key
                    break
        self._full_rows.append(new_row)
        self._renumber_item_nos()
        self._apply_table_model()
        last = len(self._full_rows) - 1
        if last >= 0:
            self._nav_select_row(last)

    def _on_tx_edit_cell(self) -> None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        m = self.table.model()
        if isinstance(m, SimpleTableModel) and m.is_row_handle_column(idx.column()):
            if m.columnCount() > 1:
                idx = m.index(idx.row(), 1)
                self.table.setCurrentIndex(idx)
        self.table.edit(idx)

    def _on_tx_move_up(self) -> None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        row = idx.row()
        if row <= 0 or row >= len(self._full_rows):
            return
        self._relocate_row_by_index(row, row - 1)

    def _on_tx_move_down(self) -> None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        row = idx.row()
        if row < 0 or row >= len(self._full_rows) - 1:
            return
        self._relocate_row_by_index(row, row + 1)

    def _on_tx_delete_row(self) -> None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        row = idx.row()
        if row < 0 or row >= len(self._full_rows):
            return
        title = "確認" if self.lang == "CHN" else "Confirm"
        msg = "刪除此列？" if self.lang == "CHN" else "Delete this row?"
        if (
            QMessageBox.question(
                self,
                title,
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        del self._full_rows[row]
        self._renumber_item_nos()
        self._apply_table_model()

    def _on_tx_copy_row(self) -> None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        row = idx.row()
        if row < 0 or row >= len(self._full_rows):
            return
        self._full_rows.insert(row + 1, list(self._full_rows[row]))
        self._renumber_item_nos()
        self._apply_table_model()
        self._nav_select_row(row + 1)

    def _nav_select_row(self, row: int) -> None:
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if m is None or row < 0 or row >= n:
            return
        idx = m.index(row, 0)
        self.table.setCurrentIndex(idx)
        self.table.selectRow(row)
        self.table.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        self._refresh_record_nav_ui()

    def _on_nav_first(self) -> None:
        self._nav_select_row(0)

    def _on_nav_prev(self) -> None:
        idx = self.table.currentIndex()
        m = self.table.model()
        if m is None or not idx.isValid():
            return
        self._nav_select_row(idx.row() - 1)

    def _on_nav_next(self) -> None:
        idx = self.table.currentIndex()
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if m is None:
            return
        if not idx.isValid() or idx.row() < 0 or idx.row() >= n:
            return
        self._nav_select_row(idx.row() + 1)

    def _on_nav_last(self) -> None:
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if n <= 0:
            return
        self._nav_select_row(n - 1)


class WorkPage(QWidget):
    """
    標準工作頁：
    - 上方搜尋列
    - 中間 QTableView Grid（至少顯示 20 列高度）
    - 下方按鈕列（搜尋/過濾/新增/更改/刪除/複製/列印/離開）
    - 採 Fusion 科技風樣式
    """

    def __init__(
        self,
        table_name: str,
        field_names: List[str],
        data_dict: DataDictionary,
        lang: LanguageCode,
        input_lang: Optional[LanguageCode] = None,
        load_data_func: Optional[Callable[[str, bool], List[List[str]]]] = None,
        backend: Optional["DbBackendBase"] = None,
        tx_files: Optional[List[str]] = None,
        on_close_tab: Optional[Callable[[], None]] = None,
        on_detail_tab: Optional[
            Callable[[Dict[str, str], List[str], LanguageCode, Optional[List[str]]], None]
        ] = None,
        on_query_tab: Optional[Callable[[str, List[str], str], None]] = None,
        do_proc: str = "",
        proc_name: Optional[str] = None,
        menu_item_title: str = "",
        form_field_names: Optional[List[str]] = None,
        physical_field_names: Optional[List[str]] = None,
        app_base_dir: Optional[str] = None,
        sys_data_mdb_path: str = "",
        print_doc_key_column: Optional[str] = None,
        user_data_mdb_path: str = "",
        company_co_key: str = "",
        group_level: Optional[int] = None,
        work_actions: Optional[WorkActionFlags] = None,
        program_work_actions: Optional[WorkActionFlags] = None,
        login_date: str = "",
        company_currency: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.table_name = table_name
        self.field_names = list(field_names)
        self.physical_fields = list(physical_field_names or field_names)
        self.form_field_names = list(
            form_field_names if form_field_names is not None else self.physical_fields
        )
        try:
            self._grid_phys_indices: List[int] = [
                self.physical_fields.index(f) for f in self.field_names
            ]
        except ValueError:
            self._grid_phys_indices = list(range(len(self.field_names)))
        self.data_dict = data_dict
        self.lang = lang
        # 顯示使用 lang
        if input_lang is None:
            self.input_lang: LanguageCode = "ENG" if lang == "CHN" else lang
        else:
            self.input_lang = input_lang
        self.load_data_func = load_data_func
        self.backend = backend
        self.tx_files = tx_files or []
        # 需求：WorkPage 主畫面不顯示 TX_FILE 的 Grid
        self._show_tx_grids_in_master: bool = False
        self.on_close_tab = on_close_tab or (lambda: None)
        self.on_detail_tab = on_detail_tab
        self.on_query_tab = on_query_tab
        self.do_proc = (do_proc or "").strip()
        _pn = (proc_name or "").strip()
        self.report_proc_name = _pn if _pn else self.do_proc
        self.menu_item_title = (menu_item_title or "").strip()
        self._app_base_dir = (
            os.path.abspath(app_base_dir) if app_base_dir else None
        )
        self.sys_data_mdb_path = (sys_data_mdb_path or "").strip()
        self._user_data_mdb_path = (user_data_mdb_path or "").strip()
        self._company_co_key = (company_co_key or "").strip()
        self._group_level = group_level
        self._login_date = (login_date or "").strip()
        self._company_currency = (company_currency or "").strip()
        # PROGRAM.KEY_CODE：主檔「由/至編號」對應之實體欄名（由選單程式列帶入）。
        self._print_doc_key_column = (print_doc_key_column or "").strip() or None
        self._current_rows: List[List[str]] = []
        self._tx_input_grids: Dict[str, QTableWidget] = {}
        self._program_work_actions = program_work_actions or WorkActionFlags()
        if work_actions is not None:
            self._work_actions = work_actions
        else:
            self._work_actions = merge_work_action_flags(
                self.data_dict.work_action_flags(self.table_name, self.do_proc),
                self._program_work_actions,
            )

        if self._app_base_dir:
            load_ui_font_settings(self._app_base_dir)

        self._build_ui()
        self._load_initial_data()
        if self._show_tx_grids_in_master:
            self._setup_master_row_sync()

    # region UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 搜尋列（上方）+ 功能按鈕列（搜尋下方、GRID 上方）
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.setContentsMargins(0, 0, 0, 0)

        def make_button(text: str, icon_key: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setIcon(icon_from_key(self.style(), icon_key))
            apply_work_action_button_style(btn)
            return btn

        if self.lang == "CHN":
            self.btn_search = make_button("搜尋", "search")
            self.btn_filter = make_button("過濾", "filter")
        else:
            self.btn_search = make_button("Search", "search")
            self.btn_filter = make_button("Filter", "filter")
        self.btn_search.clicked.connect(self._on_search_enter)
        self.btn_filter.clicked.connect(self._on_filter)
        search_row.addWidget(self.btn_filter)
        search_row.addWidget(self.btn_search)

        self.lbl_search = QLabel()
        self.lbl_search.setText(self._search_label_text())
        self.lbl_search.setStyleSheet("font-size: 12pt; font-weight: 700;")
        self.txt_search = QLineEdit()
        _disable_ime(self.txt_search)
        self.txt_search.returnPressed.connect(self._on_search_enter)
        search_row.addWidget(self.lbl_search)
        search_row.addWidget(self.txt_search, 1)
        layout.addLayout(search_row)

        if self.lang == "CHN":
            self.btn_add = make_button("新增", "add")
            self.btn_edit = make_button("更改", "edit")
            self.btn_delete = make_button("刪除", "delete")
            self.btn_copy = make_button("複製", "copy")
            self.btn_exit = make_button("離開", "exit")
            self.btn_refresh = make_button("刷新資料", "convert_db")
            self.btn_print = make_button("列印", "print")
        else:
            self.btn_add = make_button("Add", "add")
            self.btn_edit = make_button("Edit", "edit")
            self.btn_delete = make_button("Delete", "delete")
            self.btn_copy = make_button("Copy", "copy")
            self.btn_exit = make_button("Exit", "exit")
            self.btn_refresh = make_button("Refresh", "convert_db")
            self.btn_print = make_button("Print", "print")

        self.btn_exit.clicked.connect(self._on_exit)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_refresh.clicked.connect(self._on_refresh_data)
        self.btn_print.clicked.connect(self._on_print_preview)

        action_buttons: List[QPushButton] = [
            self.btn_add,
            self.btn_edit,
            self.btn_delete,
            self.btn_copy,
            self.btn_exit,
            self.btn_refresh,
            self.btn_print,
        ]
        self.btn_import: Optional[QPushButton] = None
        from core.data_import_service import is_data_import_program

        if is_data_import_program(self.do_proc):
            import_label = "資料匯入" if self.lang == "CHN" else "Data Import"
            self.btn_import = make_button(import_label, "database")
            self.btn_import.clicked.connect(self._on_data_import)
            action_buttons.append(self.btn_import)

        self.btn_attachment: Optional[QPushButton] = None
        self.btn_other: Optional[QPushButton] = None
        if self._work_actions.need_attach:
            attach_label = "附件" if self.lang == "CHN" else "Attachment"
            self.btn_attachment = make_button(attach_label, "attachment")
            self.btn_attachment.clicked.connect(self._on_attachment)
            action_buttons.append(self.btn_attachment)
        if self._work_actions.need_other:
            other_label = (self._work_actions.other_title or "").strip()
            if not other_label:
                other_label = "其他" if self.lang == "CHN" else "Other"
            self.btn_other = make_button(other_label, "other")
            self.btn_other.clicked.connect(self._on_other)
            action_buttons.append(self.btn_other)

        action_panel = QFrame()
        action_panel.setObjectName("workActionPanel")
        action_panel.setStyleSheet(work_action_panel_qss())
        self._action_panel = action_panel
        self._work_action_buttons = action_buttons
        action_row = QHBoxLayout(action_panel)
        action_row.setContentsMargins(8, 8, 8, 8)
        action_row.setSpacing(10)
        for b in action_buttons:
            action_row.addWidget(b)
        action_row.addStretch(1)
        layout.addWidget(action_panel)

        # Grid（功能按鈕列下方）
        self.table = QTableView()
        self.table.doubleClicked.connect(self._on_grid_activate)
        self._grid_visible_rows = (
            10 if self._show_tx_grids_in_master else _GRID_VISIBLE_ROWS_MAIN
        )
        configure_grid_table_view(self.table, self._grid_visible_rows, self._app_base_dir)
        self.table.installEventFilter(self)  # Enter 鍵開啟表單
        install_grid_copy_context_menu(self.table, lambda: self.lang)
        self._grid_sort_stack: List[GridSortKey] = []
        self._grid_header_base_titles: List[str] = []
        self._attach_grid_sort_header(self.table)

        layout.addWidget(self.table)

        # 資料瀏覽：首筆 / 上筆 / 下筆 / 末筆 + 紀錄位置與總數
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        self.btn_nav_first = QPushButton()
        self.btn_nav_prev = QPushButton()
        self.btn_nav_next = QPushButton()
        self.btn_nav_last = QPushButton()
        for nb in (
            self.btn_nav_first,
            self.btn_nav_prev,
            self.btn_nav_next,
            self.btn_nav_last,
        ):
            apply_nav_button_style(nb)
        self._apply_grid_nav_icons_and_tooltips()
        self.btn_nav_first.clicked.connect(self._on_nav_first)
        self.btn_nav_prev.clicked.connect(self._on_nav_prev)
        self.btn_nav_next.clicked.connect(self._on_nav_next)
        self.btn_nav_last.clicked.connect(self._on_nav_last)
        nav_row.addWidget(self.btn_nav_first)
        nav_row.addWidget(self.btn_nav_prev)
        nav_row.addWidget(self.btn_nav_next)
        nav_row.addWidget(self.btn_nav_last)
        self.lbl_record_nav = QLabel()
        self.lbl_record_nav.setStyleSheet(
            f"font-size: 11pt; font-weight: 700; color: {theme_surface_text_color()};"
        )
        nav_row.addWidget(self.lbl_record_nav, 1)
        layout.addLayout(nav_row)

        # 需求：WorkPage 不顯示 TX_FILE 的 Grid

        self.setLayout(layout)

    def _search_label_text(self) -> str:
        if self.lang == "CHN":
            return "搜尋:"
        return "Search:"

    def set_language(self, lang: LanguageCode) -> None:
        """
        供 MainWindow 切換語言時呼叫：更新 Grid 標題與搜尋介面文字。
        """
        self.lang = lang
        if hasattr(self, "lbl_search") and self.lbl_search:
            self.lbl_search.setText(self._search_label_text())

        # 只重建表頭，保留目前資料列內容
        self._refresh_grid_model_from_current_rows()

        # 同步更新主頁面的 TX_FILE 輸入 Grid 標題
        if hasattr(self, "tx_area_title"):
            self.tx_area_title.setText(
                "TX Detail Input" if self.lang == "ENG" else "交易明細輸入"
            )
        for tx_name, grid in self._tx_input_grids.items():
            self._refresh_work_tx_grid_headers(tx_name, grid)

        # 若有已開啟的表單（RecordFormDialog），同步更新其 LABEL / 視窗標題
        for dlg in self.findChildren(RecordFormDialog):
            try:
                dlg.set_language(self.lang)
            except Exception:
                pass

        self._apply_grid_nav_icons_and_tooltips()
        self._attach_grid_nav_selection()
        self._refresh_record_nav_ui()
        self._refresh_action_bar_i18n()

    def _refresh_action_bar_i18n(self) -> None:
        """切換語言時更新功能列按鈕文字與寬度。"""
        chn = self.lang == "CHN"
        pairs = [
            (getattr(self, "btn_search", None), "搜尋" if chn else "Search", "search"),
            (getattr(self, "btn_filter", None), "過濾" if chn else "Filter", "filter"),
            (getattr(self, "btn_add", None), "新增" if chn else "Add", "add"),
            (getattr(self, "btn_edit", None), "更改" if chn else "Edit", "edit"),
            (getattr(self, "btn_delete", None), "刪除" if chn else "Delete", "delete"),
            (getattr(self, "btn_copy", None), "複製" if chn else "Copy", "copy"),
            (getattr(self, "btn_exit", None), "離開" if chn else "Exit", "exit"),
            (
                getattr(self, "btn_refresh", None),
                "刷新資料" if chn else "Refresh",
                "convert_db",
            ),
            (
                getattr(self, "btn_print", None),
                "列印" if chn else "Print",
                "print",
            ),
            (
                getattr(self, "btn_attachment", None),
                "附件" if chn else "Attachment",
                "attachment",
            ),
            (
                getattr(self, "btn_import", None),
                "資料匯入" if chn else "Data Import",
                "database",
            ),
        ]
        for btn, text, icon_key in pairs:
            if btn is None:
                continue
            btn.setText(text)
            btn.setIcon(icon_from_key(self.style(), icon_key))
            apply_work_action_button_style(btn)
        if getattr(self, "btn_other", None) is not None:
            other_label = (self._work_actions.other_title or "").strip()
            if not other_label:
                other_label = "其他" if chn else "Other"
            self.btn_other.setText(other_label)
            self.btn_other.setIcon(icon_from_key(self.style(), "other"))
            apply_work_action_button_style(self.btn_other)

    def _apply_grid_nav_icons_and_tooltips(self) -> None:
        bind_grid_nav_icon_buttons(
            self.lang,
            self.style(),
            self.btn_nav_first,
            self.btn_nav_prev,
            self.btn_nav_next,
            self.btn_nav_last,
        )

    def _record_nav_label_text(self, total: int, current_1based: Optional[int]) -> str:
        return format_record_nav_label(total, current_1based)

    def _refresh_record_nav_ui(self) -> None:
        m = self.table.model()
        total = grid_model_data_row_count(m)
        cur: Optional[int] = None
        idx = self.table.currentIndex()
        if idx.isValid() and m is not None and 0 <= idx.row() < total:
            cur = idx.row() + 1
        self.lbl_record_nav.setText(self._record_nav_label_text(total, cur))
        has_rows = total > 0
        row = idx.row() if idx.isValid() and m is not None else -1
        no_sel = not idx.isValid() or row < 0 or row >= total
        self.btn_nav_first.setEnabled(has_rows and (no_sel or row > 0))
        self.btn_nav_prev.setEnabled(has_rows and not no_sel and row > 0)
        self.btn_nav_next.setEnabled(has_rows and not no_sel and row < total - 1)
        self.btn_nav_last.setEnabled(has_rows and (no_sel or row < total - 1))
        self._refresh_other_button_state()

    def _refresh_other_button_state(self) -> None:
        """發票／購貨金額 <= 已付金額時停用「其他功能」。"""
        btn = getattr(self, "btn_other", None)
        if btn is None:
            return
        row = self._get_current_full_row()
        if not row:
            btn.setEnabled(True)
            return
        try:
            from core.receipt_payment_service import is_document_fully_paid

            fully = is_document_fully_paid(self.physical_fields, row)
        except Exception:
            fully = False
        btn.setEnabled(not fully)

    def reapply_work_theme(self) -> None:
        """主題切換後重套功能按鈕、導覽鈕與 Grid 表頭樣式。"""
        panel = getattr(self, "_action_panel", None)
        if panel is not None:
            panel.setStyleSheet(work_action_panel_qss())
        for btn in getattr(self, "_work_action_buttons", []) or []:
            apply_work_action_button_style(btn)
        if hasattr(self, "btn_search") and self.btn_search is not None:
            apply_work_action_button_style(self.btn_search)
        for nb in (
            getattr(self, "btn_nav_first", None),
            getattr(self, "btn_nav_prev", None),
            getattr(self, "btn_nav_next", None),
            getattr(self, "btn_nav_last", None),
        ):
            if nb is not None:
                apply_nav_button_style(nb)
        if hasattr(self, "lbl_record_nav") and self.lbl_record_nav is not None:
            self.lbl_record_nav.setStyleSheet(
                f"font-size: 11pt; font-weight: 700; color: {theme_surface_text_color()};"
            )
        reapply_grid_fonts(self.table, self._app_base_dir)
        for tx_grid in getattr(self, "_tx_input_grids", {}).values():
            reapply_grid_fonts(tx_grid, self._app_base_dir)

    def _attach_grid_nav_selection(self) -> None:
        sm = self.table.selectionModel()
        if sm is None:
            return
        try:
            sm.selectionChanged.disconnect(self._on_grid_selection_for_nav)
        except TypeError:
            pass
        sm.selectionChanged.connect(self._on_grid_selection_for_nav)

    def _on_grid_selection_for_nav(self, *_args) -> None:
        self._refresh_record_nav_ui()

    def _nav_select_row(self, row: int) -> None:
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if m is None or row < 0 or row >= n:
            return
        _end_grid_inplace_edit(self.table)
        for g in self._tx_input_grids.values():
            _end_grid_inplace_edit(g)
        idx = m.index(row, 0)
        self.table.setCurrentIndex(idx)
        self.table.selectRow(row)
        self.table.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        if self.tx_files:
            self._sync_tx_grids_for_current_row()
        self._refresh_record_nav_ui()

    def _on_nav_first(self) -> None:
        self._nav_select_row(0)

    def _on_nav_prev(self) -> None:
        idx = self.table.currentIndex()
        m = self.table.model()
        if m is None or not idx.isValid():
            return
        self._nav_select_row(idx.row() - 1)

    def _on_nav_next(self) -> None:
        idx = self.table.currentIndex()
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if m is None:
            return
        if not idx.isValid() or idx.row() < 0 or idx.row() >= n:
            return
        self._nav_select_row(idx.row() + 1)

    def _on_nav_last(self) -> None:
        m = self.table.model()
        n = grid_model_data_row_count(m)
        if n <= 0:
            return
        self._nav_select_row(n - 1)

    def _setup_work_tx_grid(
        self,
        tx_name: str,
        tx_grid: QTableWidget,
        tx_key: Optional[str] = None,
        tx_filter_col: Optional[str] = None,
    ) -> None:
        _end_grid_inplace_edit(tx_grid)
        _disable_ime(tx_grid)
        phys: List[str] = []
        if self.backend is not None:
            phys = self.backend.list_columns(tx_name)
        if not phys:
            phys = ["LINE_NO", "ITEM_CODE", "QTY", "PRICE", "AMOUNT"]
        cols, src_idx = self.data_dict.grid_display_projection(tx_name, phys)

        tx_grid.setObjectName("appGridTable")
        tx_grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tx_grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tx_grid.setColumnCount(len(cols))
        tx_grid.setRowCount(10)
        tx_grid.setHorizontalHeaderLabels(
            [self.data_dict.get_title(tx_name, c, self.lang) for c in cols]
        )

        # 有過濾鍵值時：明細與主檔當前紀錄綁定，不可更改
        if tx_key:
            tx_grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        else:
            tx_grid.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)

        tx_grid.clearContents()

        if self.backend is not None:
            tx_key_col = None
            if tx_filter_col:
                wanted = tx_filter_col.strip().upper()
                for c in phys:
                    if c.strip().upper() == wanted:
                        tx_key_col = c
                        break
            if tx_key_col is None:
                for c in phys:
                    if c.strip().upper() == "TX_KEY":
                        tx_key_col = c
                        break

            if tx_key:
                if tx_key_col:
                    rows = self.backend.fetch_rows_where(
                        tx_name,
                        tx_key_col,
                        tx_key,
                        limit=10,
                        column_order=phys,
                    )
                else:
                    rows = []
            else:
                rows = self.backend.fetch_rows(
                    tx_name, "", False, limit=10, column_order=phys
                )
            for r, rec in enumerate(rows[: tx_grid.rowCount()]):
                for ci, pi in enumerate(src_idx):
                    if pi < len(rec):
                        raw = rec[pi]
                        f_fmt = self.data_dict.get_data_format(tx_name, cols[ci])
                        f_typ = self.data_dict.get_data_type(tx_name, cols[ci])
                        text = format_cell_display(cols[ci], raw, f_fmt, f_typ)
                        item = QTableWidgetItem(text)
                        item.setFont(_grid_cell_font(self._app_base_dir))
                        tx_grid.setItem(r, ci, item)

        _ensure_grid_cell_delegate(tx_grid)
        reapply_grid_fonts(tx_grid, self._app_base_dir)
        apply_qtablewidget_column_widths(tx_grid, tx_name, cols, self.data_dict)
        install_grid_copy_context_menu(tx_grid, lambda: self.lang)

    def _refresh_work_tx_grid_headers(self, tx_name: str, tx_grid: QTableWidget) -> None:
        phys: List[str] = []
        if self.backend is not None:
            phys = self.backend.list_columns(tx_name)
        if not phys:
            phys = ["LINE_NO", "ITEM_CODE", "QTY", "PRICE", "AMOUNT"]
        disp, _ = self.data_dict.grid_display_projection(tx_name, phys)
        if tx_grid.columnCount() != len(disp):
            tx_grid.setColumnCount(len(disp))
        tx_grid.setHorizontalHeaderLabels(
            [self.data_dict.get_title(tx_name, c, self.lang) for c in disp]
        )
        apply_qtablewidget_column_widths(tx_grid, tx_name, disp, self.data_dict)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.table and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                idx = self.table.currentIndex()
                if idx.isValid():
                    self._on_grid_activate(idx)
                return True
        return super().eventFilter(obj, event)

    # endregion

    # region Data
    def _attach_grid_sort_header(self, tv: QTableView) -> None:
        if getattr(tv, "_wolee_sort_header_attached", False):
            return
        tv._wolee_sort_header_attached = True
        hdr = tv.horizontalHeader()
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(False)
        hdr.sectionClicked.connect(self._on_grid_header_sorted)

    def _grid_column_is_numeric(self, col: int) -> bool:
        if col < 0 or col >= len(self.field_names) or not self.data_dict:
            return False
        f_name = self.field_names[col]
        f_fmt = self.data_dict.get_data_format(self.table_name, f_name)
        f_typ = self.data_dict.get_data_type(self.table_name, f_name)
        right = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return _grid_column_text_alignment(f_name, f_fmt, f_typ) == right

    def _grid_sort_value_at(self, row: Sequence[str], col: int) -> str:
        try:
            phys = self._grid_phys_indices[col]
        except (IndexError, ValueError):
            phys = col
        raw = row[phys] if phys < len(row) else ""
        if col < len(self.field_names) and self.data_dict:
            f = self.field_names[col]
            f_fmt = self.data_dict.get_data_format(self.table_name, f)
            f_typ = self.data_dict.get_data_type(self.table_name, f)
            return format_cell_display(f, raw, f_fmt, f_typ)
        return str(raw or "")

    def _apply_grid_row_sort_inplace(self) -> None:
        if not self._grid_sort_stack:
            return
        self._current_rows = sort_rows_by_stack(
            self._current_rows,
            self._grid_sort_stack,
            self._grid_sort_value_at,
            is_numeric_col=self._grid_column_is_numeric,
        )

    def _grid_sort_headers(self) -> List[str]:
        base = self._translated_headers()
        self._grid_header_base_titles = list(base)
        return [
            base[i] + sort_indicator_text(self._grid_sort_stack, i)
            for i in range(len(base))
        ]

    def _refresh_grid_model_from_current_rows(self) -> None:
        self._apply_grid_row_sort_inplace()
        model = self._make_grid_model(self._grid_sort_headers(), self._current_rows)
        _end_grid_inplace_edit(self.table)
        self.table.setModel(model)
        self._ensure_column_widths()
        self._attach_grid_nav_selection()

    def _find_row_index_by_anchor(
        self, rows: List[List[str]], anchor: List[str]
    ) -> Optional[int]:
        key_names: List[str] = []
        for k in ((self._print_doc_key_column or "").strip(), "TX_KEY", "ID"):
            if k and k.upper() not in [x.upper() for x in key_names]:
                key_names.append(k)

        for key in key_names:
            try:
                pi = next(
                    i
                    for i, name in enumerate(self.physical_fields)
                    if name.strip().upper() == key.upper()
                )
            except StopIteration:
                continue
            if pi >= len(anchor):
                continue
            want = str(anchor[pi] or "").strip()
            if not want:
                continue
            for i, row in enumerate(rows):
                if pi < len(row) and str(row[pi] or "").strip() == want:
                    return i

        norm_anchor = [str(x or "").strip() for x in anchor]
        for i, row in enumerate(rows):
            if [str(x or "").strip() for x in row[: len(norm_anchor)]] == norm_anchor:
                return i
        return None

    def _physical_row_from_form_values(self, values: Dict[str, str]) -> List[str]:
        """由表單欄位值組出與 physical_fields 對齊的一列（供儲存後定位）。"""
        out: List[str] = []
        for f in self.physical_fields:
            found = ""
            fu = str(f).strip().upper()
            for k, kv in (values or {}).items():
                if str(k).strip().upper() == fu:
                    found = str(kv or "")
                    break
            out.append(found)
        return out

    def _select_grid_row_index(self, target_idx: int) -> None:
        model = self.table.model()
        if model is None or target_idx < 0:
            return
        if target_idx >= model.data_row_count():
            return
        idx = model.index(target_idx, 0)
        self.table.setCurrentIndex(idx)
        self.table.selectRow(target_idx)
        self.table.scrollTo(idx)

    def _on_grid_header_sorted(self, col: int) -> None:
        from PyQt6.QtWidgets import QApplication

        multi = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
        )
        anchor = self._get_current_full_row()
        toggle_grid_sort_stack(self._grid_sort_stack, int(col), multi=multi)
        self._refresh_grid_model_from_current_rows()

        model = self.table.model()
        target_idx: Optional[int] = None
        if anchor:
            target_idx = self._find_row_index_by_anchor(self._current_rows, anchor)
        if target_idx is not None and model is not None:
            idx = model.index(target_idx, 0)
            self.table.setCurrentIndex(idx)
            self.table.selectRow(target_idx)
            self.table.scrollTo(idx)
        elif self.tx_files and model is not None and model.data_row_count() > 0:
            self.table.selectRow(0)
            self.table.setCurrentIndex(model.index(0, 0))

        if self.tx_files and self.table.currentIndex().isValid():
            self._sync_tx_grids_for_current_row()
        self._refresh_record_nav_ui()

    def _translated_headers(self) -> List[str]:
        return [self.data_dict.get_title(self.table_name, f, self.lang) for f in self.field_names]

    def _make_grid_model(self, headers: List[str], rows: List[List[str]]) -> SimpleTableModel:
        """Grid 顯示格式一律即時讀取 data_dict（columns.DATA_FORMAT），避免與表單快取不一致。"""
        # 可視 20 列由表格外框固定高度保留空白空間；勿用假列補滿模型。
        return SimpleTableModel(
            headers,
            rows,
            self,
            self._grid_phys_indices,
            self.field_names,
            [],
            self.data_dict,
            self.table_name,
            editable=False,
            physical_column_count=len(self.physical_fields),
            min_display_rows=0,
        )

    def _on_attachment(self) -> None:
        from core.attachment_messages import format_attach_not_found_message
        from core.attachment_service import resolve_attachments_for_row
        from ui.attachment_dialog import open_attachments
        from ui.message_dialog import show_copyable_message

        row = self._get_current_full_row()
        if not row:
            show_copyable_message(
                self,
                "提示" if self.lang == "CHN" else "Notice",
                "請先選取一筆記錄。" if self.lang == "CHN" else "Please select a row first.",
            )
            return
        lookup_col, key_value, folder, files = resolve_attachments_for_row(
            self._work_actions.attach_path,
            self._work_actions.attach_key,
            self._print_doc_key_column or "",
            self.physical_fields,
            row,
            co_key=self._company_co_key,
            do_proc=self.do_proc,
            table_name=self.table_name,
            app_base_dir=self._app_base_dir or os.path.dirname(self.sys_data_mdb_path),
        )
        chn = self.lang == "CHN"
        title = "附件" if chn else "Attachment"
        if not lookup_col:
            show_copyable_message(
                self,
                title,
                (
                    "未設定 ATTACH_KEY 或 KEY_CODE 欄位。"
                    if chn
                    else "ATTACH_KEY or KEY_CODE column is not configured."
                ),
            )
            return
        if not key_value:
            show_copyable_message(
                self,
                title,
                (
                    f"目前記錄的「{lookup_col}」為空白，無法搜尋附件。"
                    if chn
                    else f'Field "{lookup_col}" is empty; cannot search attachments.'
                ),
            )
            return
        if not files:
            show_copyable_message(
                self,
                title,
                format_attach_not_found_message(
                    self.lang,
                    key_value,
                    folder,
                    self._group_level,
                    folder_missing=bool(folder) and not os.path.isdir(folder),
                ),
            )
            return
        open_attachments(files, lang=self.lang, parent=self)

    def _on_data_import(self) -> None:
        from core.db_factory import (
            prepare_transfer_db_for_import,
            resolve_spec_transfer_folder,
        )
        from ui.data_import_dialog import open_data_import
        from ui.main_window import MainWindow

        parent = self.window()
        transfer_be = None
        company_be = self.backend
        if isinstance(parent, MainWindow):
            # 每次重新執行 DO_DATAIMPORT：強制使用規格預設 TRANSFER
            pref_folder = resolve_spec_transfer_folder(parent.base_dir)
            transfer_path, _share, t_err, _t_warn = prepare_transfer_db_for_import(
                parent.base_dir, folder=pref_folder
            )
            if t_err:
                QMessageBox.warning(self, "資料匯入", t_err)
                return
            transfer_be = parent._backend_for_db_path(transfer_path)
            binding = parent.program_repo.resolve_program_binding(self.do_proc)
            data_prg = binding.data_item
            company_path, co_err = parent._resolve_program_db_path(
                data_prg or parent.program_repo.find_by_do_proc(self.do_proc)
            )
            if not co_err and company_path:
                company_be = parent._backend_for_db_path(company_path)
        if transfer_be is None:
            QMessageBox.warning(
                self,
                "資料匯入",
                "無法連線 TRANSFER 資料庫。"
                if self.lang == "CHN"
                else "Cannot open TRANSFER database.",
            )
            return
        open_data_import(
            transfer_be,
            company_be,
            do_proc=self.do_proc,
            lang=self.lang,
            parent=self,
            base_dir=getattr(self, "_app_base_dir", "") or "",
        )

    def _on_other(self) -> None:
        from core.arap_settlement_service import is_arap_settlement_program
        from core.data_import_service import is_data_import_program
        from core.query_registry import resolve_query_kind
        from core.receipt_payment_service import is_receipt_payment_program
        from ui.arap_settlement_dialog import open_arap_settlement
        from ui.receipt_payment_dialog import open_receipt_payment

        if is_data_import_program(self.do_proc):
            self._on_data_import()
            return

        other_title = (self._work_actions.other_title or "").strip()
        title_u = other_title.upper()
        is_query_title = "查詢" in other_title or "QUERY" in title_u

        query_kind = resolve_query_kind(self.do_proc, self.table_name, other_title)

        if query_kind:
            if self.on_query_tab is None:
                QMessageBox.warning(
                    self,
                    "查詢" if self.lang == "CHN" else "Query",
                    "無法開啟查詢分頁。"
                    if self.lang == "CHN"
                    else "Cannot open query tab.",
                )
                return
            row = self._get_current_full_row() or []
            self.on_query_tab(query_kind, row, other_title)
            return

        if is_query_title:
            QMessageBox.warning(
                self,
                "查詢" if self.lang == "CHN" else "Query",
                "不支援此查詢類型（僅支援顧客／供應商查詢、存貨查詢、賬戶查詢）。"
                if self.lang == "CHN"
                else "Unsupported query type (only customer/vendor, stock and account queries are supported).",
            )
            return

        if is_receipt_payment_program(self.do_proc, self.table_name, other_title):
            row = self._get_current_full_row()
            if not row:
                QMessageBox.information(
                    self,
                    "提示" if self.lang == "CHN" else "Notice",
                    "請先選取一筆記錄。"
                    if self.lang == "CHN"
                    else "Please select a record first.",
                )
                return
            saved = open_receipt_payment(
                self.backend,
                self.do_proc,
                row,
                self.physical_fields,
                lang=self.lang,
                table_name=self.table_name,
                other_title=other_title,
                data_dict=self.data_dict,
                app_base_dir=self._app_base_dir,
                login_date=getattr(self, "_login_date", "") or "",
                parent=self,
            )
            if saved:
                self.reload_keep_current_row()
            return

        if not is_arap_settlement_program(
            self.do_proc, self.table_name, other_title
        ):
            title = other_title or (
                "其他功能" if self.lang == "CHN" else "Other"
            )
            QMessageBox.information(
                self,
                title,
                "此功能尚未設定實作內容。"
                if self.lang == "CHN"
                else "This action is not configured yet.",
            )
            return
        row = self._get_current_full_row()
        if not row:
            QMessageBox.information(
                self,
                "提示" if self.lang == "CHN" else "Notice",
                "請先選取一筆傳票記錄。"
                if self.lang == "CHN"
                else "Please select a voucher record first.",
            )
            return
        open_arap_settlement(
            self.backend,
            self.do_proc,
            row,
            self.physical_fields,
            lang=self.lang,
            table_name=self.table_name,
            other_title=other_title,
            parent=self,
        )

    def refresh_after_data_dictionary_reload(self) -> None:
        """資料字典重新載入後：重讀 columns、更新 Grid／表單欄位並重繪。"""
        self.data_dict.reload_columns_for_table(self.table_name)
        self._work_actions = merge_work_action_flags(
            self.data_dict.work_action_flags(self.table_name, self.do_proc),
            self._program_work_actions,
        )
        self.field_names = self.data_dict.grid_columns_for_table(
            self.table_name, self.physical_fields
        )
        self.form_field_names = self.data_dict.edit_columns_for_table(
            self.table_name, self.physical_fields
        )
        try:
            self._grid_phys_indices = [
                self.physical_fields.index(f) for f in self.field_names
            ]
        except ValueError:
            self._grid_phys_indices = list(range(len(self.field_names)))
        self._refresh_grid_model_from_current_rows()
        for dlg in self.findChildren(RecordFormDialog):
            dlg.refresh_data_formats_from_dict()
        self._attach_grid_nav_selection()
        self._refresh_record_nav_ui()

    def _load_initial_data(self) -> None:
        rows: List[List[str]] = []
        if self.load_data_func:
            rows = self.load_data_func("", False)
        self._current_rows = rows
        self._refresh_grid_model_from_current_rows()
        model = self.table.model()
        if self.tx_files and model is not None and model.data_row_count() > 0:
            # 初始化時先選第一筆，讓 TX 明細能立即依 TX_KEY 過濾
            self.table.selectRow(0)
            self._sync_tx_grids_for_current_row()
        self._attach_grid_nav_selection()
        self._refresh_record_nav_ui()

    def reload_keep_current_row(
        self, anchor: Optional[Sequence[str]] = None
    ) -> None:
        """
        重新載入後定位到指定列（或原本那筆），不自動跳第一筆。
        比對優先順序：KEY_CODE / TX_KEY / ID，再退回整列比對。
        新增／複製儲存後應傳入新紀錄的 physical row 作為 anchor。
        """
        if anchor is None:
            anchor_list = self._get_current_full_row()
        else:
            anchor_list = [str(x or "") for x in anchor]
        rows: List[List[str]] = []
        if self.load_data_func:
            rows = self.load_data_func("", False)
        self._current_rows = rows
        self._refresh_grid_model_from_current_rows()

        target_idx: Optional[int] = None
        if anchor_list and any(str(x or "").strip() for x in anchor_list):
            target_idx = self._find_row_index_by_anchor(rows, list(anchor_list))

        if target_idx is not None:
            self._select_grid_row_index(target_idx)
        elif self.tx_files:
            model = self.table.model()
            if model is not None and model.data_row_count() > 0:
                self._select_grid_row_index(0)

        if self.tx_files and self.table.currentIndex().isValid():
            self._sync_tx_grids_for_current_row()
        self._refresh_record_nav_ui()

    def _ensure_column_widths(self) -> None:
        apply_grid_column_width_limits(self.table)
        apply_grid_visible_row_count(
            self.table,
            getattr(self, "_grid_visible_rows", _GRID_VISIBLE_ROWS_MAIN),
        )

    # endregion

    def _setup_master_row_sync(self) -> None:
        """監聽主檔 Grid 選取變更，刷新 TX_FILE 明細。"""
        if not self.tx_files:
            return
        try:
            sel = self.table.selectionModel()
            if sel is not None:
                sel.currentRowChanged.connect(lambda *_: self._sync_tx_grids_for_current_row())
        except Exception:
            pass

    def _get_master_tx_key_from_current_row(self) -> tuple[Optional[str], Optional[str]]:
        """
        取得目前主檔列用於過濾 TX_FILE 的鍵值：
        1) 優先用 PROGRAM.KEY_CODE 對應欄位
        2) 若無則回退主檔 TX_KEY
        回傳 (鍵欄位名, 鍵值)；任一為 None 代表無法過濾。
        """
        if not self.tx_files:
            return None, None
        full = self._get_current_full_row()
        if not full:
            return None, None

        preferred = (self._print_doc_key_column or "").strip()
        if preferred:
            pkey = preferred.upper()
            for i, name in enumerate(self.physical_fields):
                if name.strip().upper() == pkey and i < len(full):
                    v = (full[i] or "").strip()
                    if v:
                        return name, v

        for i, name in enumerate(self.physical_fields):
            if name.strip().upper() == "TX_KEY" and i < len(full):
                v = (full[i] or "").strip()
                if v:
                    return name, v
        return None, None

    def _sync_tx_grids_for_current_row(self) -> None:
        """根據目前主檔列（KEY_CODE 優先）過濾並鎖定 TX 明細。"""
        if not self.tx_files or self.backend is None:
            return

        tx_key_col, tx_key = self._get_master_tx_key_from_current_row()

        # 若主檔沒有可用鍵值，清掉明細以避免顯示錯誤資料
        if not tx_key:
            for grid in self._tx_input_grids.values():
                _end_grid_inplace_edit(grid)
                grid.clearContents()
            return

        for tx_name, grid in self._tx_input_grids.items():
            self._setup_work_tx_grid(
                tx_name,
                grid,
                tx_key=tx_key,
                tx_filter_col=tx_key_col,
            )

    # region Event handlers
    def _on_search_enter(self) -> None:
        keyword = self.txt_search.text().strip()
        if not self.load_data_func:
            return
        # 搜尋: 移到相關紀錄, 不過濾
        rows = self.load_data_func("", False)
        self._current_rows = rows
        self._refresh_grid_model_from_current_rows()
        model = self.table.model()

        self._attach_grid_nav_selection()
        if keyword:
            if not self._navigate_by_search_ret(keyword, model):
                return
        elif self.tx_files and model.data_row_count() > 0:
            self.table.selectRow(0)
            self.table.setCurrentIndex(model.index(0, 0))
        if self.tx_files and self.table.currentIndex().isValid():
            self._sync_tx_grids_for_current_row()
        self._refresh_record_nav_ui()

    def _navigate_by_search_ret(self, keyword: str, model) -> bool:
        """
        SEARCH_RET 有資料時：LOOKUP_DB／LOOKUP_KEY 查找後，以回存值定位主檔列。
        回傳 False 表示已顯示找不到並中止；True 表示可繼續後續 UI 更新。
        """
        from core.search_ret_lookup import (
            find_row_by_field_value,
            resolve_search_ret_via_lookup,
        )

        phys = list(getattr(self, "physical_field_names", None) or [])
        dest, value, err = resolve_search_ret_via_lookup(
            data_dict=self.data_dict,
            backend=self.backend,
            table_name=self.table_name,
            keyword=keyword,
            lang=self.lang,
        )
        if err:
            title = "搜尋" if self.lang == "CHN" else "Search"
            QMessageBox.information(self, title, err)
            return False
        if dest and value:
            r_idx = find_row_by_field_value(self._current_rows, phys, dest, value)
            if r_idx < 0:
                msg = (
                    f"找不到「{dest}」=「{value}」的紀錄。"
                    if self.lang == "CHN"
                    else f"No record with {dest}={value}."
                )
                title = "搜尋" if self.lang == "CHN" else "Search"
                QMessageBox.information(self, title, msg)
                return False
            self.table.selectRow(r_idx)
            self.table.setCurrentIndex(model.index(r_idx, 0))
            self.table.scrollTo(model.index(r_idx, 0))
            return True

        # 無 SEARCH_RET 規則：一般關鍵字搜尋
        keyword_lower = keyword.lower()
        for r_idx, row in enumerate(self._current_rows):
            if any(keyword_lower in str(c).lower() for c in row):
                self.table.selectRow(r_idx)
                self.table.setCurrentIndex(model.index(r_idx, 0))
                self.table.scrollTo(model.index(r_idx, 0))
                break
        return True

    def _on_filter(self) -> None:
        keyword = self.txt_search.text().strip()
        if not self.load_data_func:
            return
        from core.search_ret_lookup import (
            find_row_by_field_value,
            resolve_search_ret_via_lookup,
        )

        # 過濾: SEARCH_RET 有規則時先 LOOKUP 解析，再只留對應 SEARCH_RET 欄位列
        if keyword:
            dest, value, err = resolve_search_ret_via_lookup(
                data_dict=self.data_dict,
                backend=self.backend,
                table_name=self.table_name,
                keyword=keyword,
                lang=self.lang,
            )
            if err:
                title = "過濾" if self.lang == "CHN" else "Filter"
                QMessageBox.information(self, title, err)
                return
            if dest and value:
                all_rows = self.load_data_func("", False)
                phys = list(getattr(self, "physical_field_names", None) or [])
                idx = find_row_by_field_value(all_rows, phys, dest, value)
                # 收集所有符合（精確）列
                dest_i = next(
                    (
                        i
                        for i, n in enumerate(phys)
                        if (n or "").strip().upper() == dest.strip().upper()
                    ),
                    -1,
                )
                if dest_i >= 0:
                    want = value.strip().lower()
                    rows = [
                        rec
                        for rec in all_rows
                        if dest_i < len(rec)
                        and str(rec[dest_i] or "").strip().lower() == want
                    ]
                else:
                    rows = [all_rows[idx]] if idx >= 0 else []
                if not rows:
                    msg = (
                        f"找不到「{dest}」=「{value}」的紀錄。"
                        if self.lang == "CHN"
                        else f"No record with {dest}={value}."
                    )
                    title = "過濾" if self.lang == "CHN" else "Filter"
                    QMessageBox.information(self, title, msg)
                    return
                self._current_rows = rows
                self._refresh_grid_model_from_current_rows()
                model = self.table.model()
                self._attach_grid_nav_selection()
                if model is not None and model.data_row_count() > 0:
                    self.table.selectRow(0)
                    if self.tx_files:
                        self._sync_tx_grids_for_current_row()
                self._refresh_record_nav_ui()
                return

        rows = self.load_data_func(keyword, True)
        self._current_rows = rows
        self._refresh_grid_model_from_current_rows()
        model = self.table.model()
        self._attach_grid_nav_selection()
        if self.tx_files and model is not None and model.data_row_count() > 0:
            self.table.selectRow(0)
            self._sync_tx_grids_for_current_row()
        self._refresh_record_nav_ui()

    def _get_current_full_row(self) -> Optional[List[str]]:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        model: SimpleTableModel = self.table.model()  # type: ignore[assignment]
        row = idx.row()
        try:
            return [str(x) for x in model._rows[row]]
        except Exception:
            return None

    def _form_values_from_full_row(self, full_row: List[str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for f in self.form_field_names:
            try:
                i = self.physical_fields.index(f)
                raw = str(full_row[i]) if i < len(full_row) else ""
                f_fmt = self.data_dict.get_data_format(self.table_name, f)
                f_typ = self.data_dict.get_data_type(self.table_name, f)
                out[f] = format_cell_display(f, raw, f_fmt, f_typ)
            except Exception:
                out[f] = ""
        return out

    def _insert_master_with_defaults(
        self, field_names: List[str], row_values: List[str]
    ) -> bool:
        if not self.backend:
            return False
        ins_fields, ins_values = apply_insert_bit_defaults(
            self.physical_fields,
            list(field_names),
            list(row_values),
            is_boolean_column=lambda f: is_boolean_data_type(
                self.data_dict.get_data_type(self.table_name, f)
            ),
        )
        return bool(self.backend.insert_one(self.table_name, ins_fields, ins_values))

    def _resolve_dialog_update_where(
        self, old_row: List[str]
    ) -> tuple[List[str], List[str]]:
        """優先用 KEY_CODE／報價編號／TX_KEY 等穩定鍵作 WHERE。"""
        return resolve_update_where(
            self.physical_fields,
            old_row,
            print_doc_key_column=self._print_doc_key_column,
            form_fields=self.form_field_names,
        )

    def _delete_master_row(self, old_row: List[str]) -> bool:
        if not self.backend:
            return False
        where_fields, where_vals = self._resolve_dialog_update_where(old_row)
        if not where_fields or not where_vals:
            return False
        if self.tx_files and len(where_fields) == 1:
            tx_ok, _ = delete_tx_rows_for_master(
                self.backend,
                self.tx_files,
                where_fields[0],
                where_vals[0],
            )
            if not tx_ok:
                return False
        return bool(
            self.backend.delete_one(self.table_name, where_fields, where_vals)
        )

    def _on_grid_activate(self, index: QModelIndex) -> None:
        """雙擊 / Enter：開啟右側明細分頁（若有 callback）；否則開啟編輯對話框。"""
        if not index.isValid():
            return
        row = index.row()
        model: SimpleTableModel = self.table.model()  # type: ignore[assignment]
        if row < 0 or row >= model.data_row_count():
            return
        full_row = [str(x) for x in model._rows[row]]
        values = self._form_values_from_full_row(full_row)
        old_row = full_row

        if self.on_detail_tab is not None:
            self.on_detail_tab(values, old_row, self.lang, None)
            return

        self._open_record_dialog(index, values, old_row)

    def _open_record_dialog(
        self,
        index: QModelIndex,
        values: Optional[Dict[str, str]] = None,
        old_row: Optional[List[str]] = None,
    ) -> None:
        if not index.isValid():
            return
        row = index.row()
        model: SimpleTableModel = self.table.model()  # type: ignore[assignment]
        if row < 0 or row >= model.data_row_count():
            return
        full_row = [str(x) for x in model._rows[row]]
        if values is None:
            values = self._form_values_from_full_row(full_row)
        if old_row is None:
            old_row = full_row

        def on_save(new_vals: Dict[str, str], is_new: bool) -> bool:
            vals = [new_vals.get(f, "") for f in self.form_field_names]
            if is_new:
                ok = self._insert_master_with_defaults(self.form_field_names, vals)
            else:
                where_fields, where_vals = self._resolve_dialog_update_where(old_row)
                ok = self.backend and self.backend.update_one(
                    self.table_name,
                    self.form_field_names,
                    vals,
                    where_fields,
                    where_vals,
                )
            if ok:
                if is_new:
                    self.reload_keep_current_row(
                        self._physical_row_from_form_values(new_vals)
                    )
                else:
                    self.reload_keep_current_row()
            return bool(ok)

        dlg = RecordFormDialog(
            self.table_name,
            self.form_field_names,
            values,
            self.data_dict,
            self.lang,
            is_new=False,
            on_save=on_save,
            tx_files=self.tx_files,
            backend=self.backend,
            menu_item_title=self.menu_item_title,
            do_proc=getattr(self, "do_proc", "") or "",
            proc_name=getattr(self, "report_proc_name", "") or "",
            parent=self,
        )
        dlg.open()

    def _clear_key_fields_for_copy(self, values: Dict[str, str]) -> Dict[str, str]:
        """
        複製時清空 EDIT_TYPE=ED 欄位，並清空主鍵候選欄，避免與來源單衝突。
        """
        extra = [
            (self._print_doc_key_column or "").strip(),
            "TX_KEY",
            "ID",
        ]
        return self.data_dict.clear_values_for_copy(
            self.table_name,
            values,
            also_clear_fields=extra,
        )

    def _on_add(self) -> None:
        values = empty_form_values_for_add_from_dict(
            self.data_dict,
            self.table_name,
            self.form_field_names,
            login_date=getattr(self, "_login_date", "") or "",
            company_currency=getattr(self, "_company_currency", "") or "",
            proc_name=getattr(self, "report_proc_name", "") or "",
            do_proc=getattr(self, "do_proc", "") or "",
        )
        if self.on_detail_tab is not None:
            # 右側新建明細 TAB（空表單＋日期／數字預設）；old_row=[] 表示新增／insert
            self.on_detail_tab(values, [], self.lang, None)
            return

        def on_save(new_vals: Dict[str, str], is_new: bool) -> bool:
            vals = [new_vals.get(f, "") for f in self.form_field_names]
            ok = self._insert_master_with_defaults(self.form_field_names, vals)
            if ok:
                self.reload_keep_current_row(
                    self._physical_row_from_form_values(new_vals)
                )
            return bool(ok)

        dlg = RecordFormDialog(
            self.table_name,
            self.form_field_names,
            values,
            self.data_dict,
            self.lang,
            is_new=True,
            on_save=on_save,
            tx_files=self.tx_files,
            backend=self.backend,
            menu_item_title=self.menu_item_title,
            do_proc=getattr(self, "do_proc", "") or "",
            proc_name=getattr(self, "report_proc_name", "") or "",
            parent=self,
        )
        dlg.open()

    def _on_edit(self) -> None:
        """更改：與 Enter／雙擊相同，開啟右側明細分頁（輸入介面＋TX）。"""
        index = self.table.currentIndex()
        if not index.isValid():
            return
        self._on_grid_activate(index)

    def _on_copy(self) -> None:
        index = self.table.currentIndex()
        if not index.isValid():
            return
        row = index.row()
        model: SimpleTableModel = self.table.model()  # type: ignore[assignment]
        if row < 0 or row >= model.data_row_count():
            return
        full_row = [str(x) for x in model._rows[row]]
        values = self._clear_key_fields_for_copy(self._form_values_from_full_row(full_row))
        if self.on_detail_tab is not None:
            # 右側新建明細 TAB；old_row=[] 表示複製後以新增儲存；full_row 供載入來源明細
            self.on_detail_tab(values, [], self.lang, full_row)
            return

        def on_save(new_vals: Dict[str, str], is_new: bool) -> bool:
            vals = [new_vals.get(f, "") for f in self.form_field_names]
            ok = self._insert_master_with_defaults(self.form_field_names, vals)
            if ok:
                self.reload_keep_current_row(
                    self._physical_row_from_form_values(new_vals)
                )
            return bool(ok)

        dlg = RecordFormDialog(
            self.table_name,
            self.form_field_names,
            values,
            self.data_dict,
            self.lang,
            is_new=True,
            on_save=on_save,
            tx_files=self.tx_files,
            backend=self.backend,
            menu_item_title=self.menu_item_title,
            do_proc=getattr(self, "do_proc", "") or "",
            proc_name=getattr(self, "report_proc_name", "") or "",
            parent=self,
        )
        dlg.open()

    def _on_delete(self) -> None:
        row_vals = self._get_current_full_row()
        if not row_vals:
            QMessageBox.information(self, "提示", "請先選取一筆記錄。")
            return
        if QMessageBox.question(
            self, "確認刪除", "確定要刪除所選記錄嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        if self.backend and self._delete_master_row(row_vals):
            self._load_initial_data()
            QMessageBox.information(self, "提示", "已刪除。")
        else:
            err = ""
            if self.backend is not None:
                err = str(getattr(self.backend, "last_error", "") or "").strip()
            msg = "刪除失敗。"
            if err:
                msg = f"{msg}\n\nDetail: {err}"
            QMessageBox.warning(self, "錯誤", msg)

    def _on_print_preview(self) -> None:
        from ui.print_report_dialog import PrintReportDialog

        do_proc_up = self.do_proc.strip().upper()
        table_up = (self.table_name or "").strip().upper()
        # 報價作業：DO_PROC/REPORT 流程含 DO_PRNQUOTATION，或 WORK_FILE 為 QUOTATION，皆視為報價單列印流程。
        is_quot = (
            (do_proc_up == "QUOTATION")
            or (table_up == "QUOTATION")
            or ("PRNQUOTATION" in do_proc_up)
        )
        if is_quot:
            model: SimpleTableModel = self.table.model()  # type: ignore[assignment]
            if not model or model.data_row_count() == 0:
                QMessageBox.information(self, "列印", "無資料可列印。")
                return

        inv_col_idx: Optional[int] = None
        default_inv: Optional[str] = None
        row = self._get_current_full_row()
        key_col = self._print_doc_key_column
        if key_col:
            key_i = _physical_field_index(self.physical_fields, key_col)
            if key_i is not None:
                inv_col_idx = key_i
                if row is not None and key_i < len(row):
                    t = (row[key_i] or "").strip()
                    if t:
                        default_inv = t
        if self.tx_files:
            tx_i: Optional[int] = None
            for i, name in enumerate(self.physical_fields):
                if name.strip().upper() == "TX_KEY":
                    tx_i = i
                    break
            if inv_col_idx is None and tx_i is not None:
                inv_col_idx = tx_i
            if (
                default_inv is None
                and tx_i is not None
                and row is not None
                and tx_i < len(row)
            ):
                t = (row[tx_i] or "").strip()
                if t:
                    default_inv = t

        dlg = PrintReportDialog(
            self,
            self.lang,
            self.table_name,
            self.physical_fields,
            self.field_names,
            self.data_dict,
            self.backend,
            self.report_proc_name,
            self.sys_data_mdb_path,
            self._app_base_dir,
            self.menu_item_title,
            quotation_xls_mode=is_quot,
            quotation_current_row=list(row) if (is_quot and row is not None) else None,
            inv_column_index=inv_col_idx,
            default_inv_text=default_inv,
            user_data_mdb_path=self._user_data_mdb_path,
            company_co_key=self._company_co_key,
        )
        dlg.exec()

    def _on_refresh_data(self) -> None:
        """刷新資料：重新載入 GRID，盡量保留目前選取列。"""
        self.reload_keep_current_row()

    def _on_exit(self) -> None:
        self.on_close_tab()

    # endregion


class RecordFormDialog(QDialog):
    """
    動態表單: 兩欄排版，一般欄標題 12pt 靠右、輸入 11pt 在右側；
    備註／長文字為單一橫列（標題區在左且標題文字靠右、輸入靠右佔滿剩餘寬），可捲動；儲存時呼叫 on_save，取消則關閉不儲存。
    """

    def __init__(
        self,
        table_name: str,
        field_names: List[str],
        values: Dict[str, str],
        data_dict: DataDictionary,
        lang: LanguageCode,
        is_new: bool = False,
        on_save: Optional[Callable[[Dict[str, str], bool], bool]] = None,
        tx_files: Optional[List[str]] = None,
        backend: Optional["DbBackendBase"] = None,
        menu_item_title: str = "",
        do_proc: str = "",
        proc_name: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.table_name = table_name
        self.field_names = field_names
        self.values = values
        self.data_dict = data_dict
        self.lang = lang
        self.is_new = is_new
        self.on_save = on_save
        self.tx_files = tx_files or []
        self.backend = backend
        self._app_base_dir = os.path.dirname(os.path.abspath(data_dict.mdb_path))
        self._menu_item_title = (menu_item_title or "").strip()
        self._do_proc = (do_proc or "").strip()
        self._proc_name = (proc_name or "").strip()
        self._form_tab_widget: Optional[QTabWidget] = None
        self._form_tab_keys: List[str] = []
        self._master_tx_key: Optional[str] = None
        for f in self.field_names:
            if f.strip().upper() == "TX_KEY":
                v = (self.values.get(f) or "").strip()
                self._master_tx_key = v or None
                break

        self.setWindowTitle(self._build_title())
        self.resize(720, 680)

        self._build_ui()
        self._install_form_field_navigation()
        self._install_search_ret_hooks()
        self._install_arap_vou_locks()

    def _install_search_ret_hooks(self) -> None:
        install_form_search_ret_hooks(
            self,
            data_dict=self.data_dict,
            backend=self.backend,
            table_name=self.table_name,
            field_names=self.field_names,
            editors=self._editors,
            lang=self.lang,
        )

    def _arap_proc_name(self) -> str:
        return (getattr(self, "_proc_name", None) or getattr(self, "report_proc_name", None) or "") or ""

    def _arap_do_proc(self) -> str:
        return (getattr(self, "_do_proc", None) or getattr(self, "do_proc", None) or "") or ""

    def _refresh_arap_vou_locks(self) -> None:
        _refresh_form_arap_vou_locks(
            field_meta=getattr(self, "_field_meta", []) or [],
            editors=getattr(self, "_editors", {}) or {},
            data_dict=self.data_dict,
            table_name=self.table_name,
            is_new_record=bool(getattr(self, "is_new", False)),
            base_dir=getattr(self, "_app_base_dir", None),
            proc_name=self._arap_proc_name(),
            do_proc=self._arap_do_proc(),
        )

    def _install_arap_vou_locks(self) -> None:
        _install_arap_vou_type_lock_hooks(
            getattr(self, "_editors", {}) or {},
            proc_name=self._arap_proc_name(),
            do_proc=self._arap_do_proc(),
            on_change=self._refresh_arap_vou_locks,
        )

    def _install_form_field_navigation(self) -> None:
        """QLineEdit / QDateEdit / QTextEdit：Enter／下鍵 → 下一欄；上鍵 → 上一欄。"""
        self._line_edit_order: List[QLineEdit] = []
        self._line_edit_field: Dict[QLineEdit, str] = {}
        self._form_nav_widgets: set = set()
        self._form_nav_proxy: Dict[QWidget, QWidget] = {}
        for f in self.field_names:
            ed = self._editors.get(f)
            if isinstance(ed, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
                if isinstance(ed, QLineEdit):
                    self._line_edit_field[ed] = f
                    self._line_edit_order.append(ed)
                self._form_nav_widgets.add(ed)
                try:
                    ed.installEventFilter(self)
                except Exception:
                    pass
                _form_bind_composite_nav_proxy(self, ed, self._form_nav_proxy)
        # 內部編輯列可能延遲建立，再補掛一次
        QTimer.singleShot(0, self._rebind_form_composite_nav_proxy)

    def _rebind_form_composite_nav_proxy(self) -> None:
        proxy = getattr(self, "_form_nav_proxy", None)
        if not isinstance(proxy, dict):
            return
        for ed in getattr(self, "_form_nav_widgets", set()) or set():
            _form_bind_composite_nav_proxy(self, ed, proxy)

    def eventFilter(self, obj, event) -> bool:
        nav_widgets = getattr(self, "_form_nav_widgets", set())
        proxy = getattr(self, "_form_nav_proxy", {})
        if event.type() == QEvent.Type.FocusIn:
            host_ed = _form_resolve_nav_editor(obj, nav_widgets, proxy)
            if host_ed is not None:
                _form_bind_composite_nav_proxy(self, host_ed, proxy)
        nav_obj = _form_resolve_nav_editor(obj, nav_widgets, proxy)
        if (
            event.type() == QEvent.Type.KeyPress
            and isinstance(nav_obj, (QLineEdit, QDateEdit, QTextEdit, QComboBox))
        ):
            key = event.key()
            if key in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Down,
                Qt.Key.Key_Right,
            ):
                field = getattr(self, "_line_edit_field", {}).get(nav_obj) if isinstance(nav_obj, QLineEdit) else None
                if field is None:
                    for f, ed in self._editors.items():
                        if ed is nav_obj:
                            field = f
                            break
                if field and not apply_form_field_search_ret(
                    host=self,
                    data_dict=self.data_dict,
                    backend=self.backend,
                    table_name=self.table_name,
                    field=field,
                    editors=self._editors,
                    lang=self.lang,
                ):
                    return True
            if _handle_form_field_key_nav(
                self.field_names,
                self._editors,
                nav_widgets,
                nav_obj,
                event,
                getattr(self, "_tx_tabs", None),
                getattr(self, "_save_button", None),
                getattr(self, "_form_tab_widget", None),
            ):
                return True
        return super().eventFilter(obj, event)

    def _build_title(self) -> str:
        base = self.data_dict.get_title(self.table_name, self.table_name, self.lang)
        if self.is_new:
            return f"新增 - {base}"
        return f"編輯 - {base}"

    def _menu_base_title(self) -> str:
        base = (self._menu_item_title or "").strip()
        if base:
            return base
        return self.data_dict.get_title(self.table_name, self.table_name, self.lang)

    def _form_tab_title(self, idx1: int, total_tabs: int = 1) -> str:
        base = self._menu_base_title()
        if self.lang == "CHN":
            if total_tabs <= 1:
                return f"{base} 資 料"
            return f"{base} 資 料 - {idx1}"
        if total_tabs <= 1:
            return f"{base} Data"
        return f"{base} Data - {idx1}"

    def _form_tab_title_by_key(self, tab_key: str, idx1: int, total_tabs: int) -> str:
        return _form_tab_title_for_key(
            tab_key,
            idx1,
            total_tabs,
            lang=self.lang,
            menu_base=self._menu_base_title(),
        )

    def _detail_tab_title(self, idx1: int, total_tabs: int = 1) -> str:
        base = self._menu_base_title()
        if self.lang == "CHN":
            if total_tabs <= 1:
                return f"{base} 明 細"
            return f"{base} 明 細 - {idx1}"
        if total_tabs <= 1:
            return f"{base} Detail"
        return f"{base} Detail - {idx1}"

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(4)
        self._editors: Dict[str, QWidget] = {}
        self._labels: Dict[str, QLabel] = {}
        self._tx_tables: Dict[str, TxDetailGridPane] = {}
        self._form_layout_mode = get_form_layout_mode(self._app_base_dir)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(4, 4, 4, 4)
        form_layout.setSpacing(4)

        # 欄位間距：比先前更緊密，避免表單看起來太鬆
        grid_vertical_spacing = 0
        grid_horizontal_spacing = 8

        # 先把所有欄位的 label/editor 建起來，再依 2／3 欄規格分 TAB。
        field_meta: List[Dict[str, object]] = []
        for field in self.field_names:
            title = self.data_dict.get_title(self.table_name, field, self.lang)
            label = QLabel(_form_label_caption(title))
            label.setStyleSheet(form_label_style(self._app_base_dir))
            label.setAlignment(_form_label_align_vcenter())
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._labels[field] = label

            f_fmt = self.data_dict.get_data_format(self.table_name, field)
            f_typ = self.data_dict.get_data_type(self.table_name, field)
            is_long = _is_long_text_field(field, f_typ)
            combo_choices = self.data_dict.get_combo_choices(self.table_name, field)
            use_combo = self.data_dict.field_uses_combo(self.table_name, field)
            editor = _create_form_editor(
                field,
                f_fmt,
                f_typ,
                combo_choices=combo_choices,
                use_combo=use_combo,
            )
            _disable_ime(editor)
            editor.setStyleSheet(form_editor_style(self._app_base_dir))
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            _apply_form_editor_dimensions(editor, self._form_layout_mode)
            _init_form_editor_value(
                editor, field, self.values.get(field, ""), f_fmt, f_typ
            )
            self._editors[field] = editor

            display: QWidget = editor
            lookup_db, lookup_key, lookup_ret = self.data_dict.get_lookup(
                self.table_name, field
            )
            if (lookup_key or "").strip() and (lookup_db or "").strip():
                display = _wrap_lookup_field_editor(
                    editor,
                    on_lookup=lambda *_a, f=field, db=lookup_db, ret=lookup_ret: self._open_lookup(
                        f, db, ret
                    ),
                    lang=self.lang,
                )
            apply_form_field_edit_state(
                field,
                editor,
                display,
                data_dict=self.data_dict,
                table_name=self.table_name,
                is_new_record=self.is_new,
                base_dir=self._app_base_dir,
            )

            field_meta.append(
                {
                    "field": field,
                    "is_long": is_long,
                    "label": label,
                    "editor": editor,
                    "display": display,
                }
            )

        self._field_meta = field_meta
        _apply_form_label_widths_for_mode(
            self._labels,
            {
                f: self.data_dict.get_title(self.table_name, f, self.lang)
                for f in self.field_names
            },
            base_dir=self._app_base_dir,
            layout_mode=self._form_layout_mode,
        )

        tab_widget = QTabWidget()
        self._form_tab_widget = tab_widget
        self._form_tab_keys = _populate_form_tab_widget(
            tab_widget,
            self._field_meta,
            table_name=self.table_name,
            data_dict=self.data_dict,
            layout_mode=self._form_layout_mode,
            labels_by_field=self._labels,
            tab_title_fn=self._form_tab_title_by_key,
        )
        form_layout.addWidget(tab_widget)

        scroll.setWidget(form_container)
        main_layout.addWidget(scroll, 1)

        # 儲存 / 取消 按鈕（放在明細 Grid 上方）
        btn_row = QHBoxLayout()
        self._layout_toggle_button = QPushButton()
        apply_work_action_button_style(self._layout_toggle_button)
        self._layout_toggle_button.clicked.connect(self._toggle_form_layout_mode)
        self._refresh_layout_toggle_button()
        btn_row.addWidget(self._layout_toggle_button)
        btn_row.addStretch(1)
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._do_save)
        btn_box.rejected.connect(self.reject)
        save_btn = btn_box.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        for pb in (save_btn, cancel_btn):
            if pb is not None:
                apply_work_action_button_style(pb)
        if save_btn is not None:
            save_btn.setText("儲存" if self.lang == "CHN" else "Save")
            save_btn.setIcon(icon_from_key(self.style(), "save"))
        if cancel_btn is not None:
            cancel_btn.setText("取消" if self.lang == "CHN" else "Cancel")
            cancel_btn.setIcon(icon_from_key(self.style(), "cancel"))
        btn_row.addWidget(btn_box)
        btn_row.addStretch(1)
        main_layout.addLayout(btn_row)
        self._save_button = save_btn
        self._cancel_button = cancel_btn

        # TX_FILE 明細 Grid 置於表單下方；無 TX 時下方仍佔 50% 留白
        if self.tx_files:
            self._tx_tabs = QTabWidget()
            for tx_name in self.tx_files:
                pane = TxDetailGridPane(
                    tx_name,
                    self.data_dict,
                    self.lang,
                    self.backend,
                    self._master_tx_key,
                    parent=self,
                )
                self._tx_tables[tx_name] = pane
                self._tx_tabs.addTab(pane, tx_name)
            tx_tab_count = self._tx_tabs.count()
            for i in range(tx_tab_count):
                self._tx_tabs.setTabText(i, self._detail_tab_title(i + 1, tx_tab_count))
            from core.ui_theme import apply_tab_title_colors

            apply_tab_title_colors(self._tx_tabs)
            main_layout.addWidget(self._tx_tabs, 1)
        else:
            bottom_placeholder = QWidget()
            bottom_placeholder.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            main_layout.addWidget(bottom_placeholder, 1)
        main_layout.setStretchFactor(scroll, 1)

    def set_language(self, lang: LanguageCode) -> None:
        self.lang = lang
        self.setWindowTitle(self._build_title())
        for field, label in self._labels.items():
            label.setText(
                _form_label_caption(
                    self.data_dict.get_title(self.table_name, field, self.lang)
                )
            )
        if self._form_tab_widget is not None:
            form_tab_count = self._form_tab_widget.count()
            for i in range(form_tab_count):
                key = self._form_tab_keys[i] if i < len(self._form_tab_keys) else ""
                self._form_tab_widget.setTabText(
                    i, self._form_tab_title_by_key(key, i + 1, form_tab_count)
                )
        if hasattr(self, "_tx_tabs") and self._tx_tabs is not None:
            tx_tab_count = self._tx_tabs.count()
            for i in range(tx_tab_count):
                self._tx_tabs.setTabText(i, self._detail_tab_title(i + 1, tx_tab_count))
            from core.ui_theme import apply_tab_title_colors

            apply_tab_title_colors(self._tx_tabs)
        if self._form_tab_widget is not None:
            from core.ui_theme import apply_tab_title_colors

            apply_tab_title_colors(self._form_tab_widget)
        for pane in self._tx_tables.values():
            pane.set_language(self.lang)
        if getattr(self, "_save_button", None) is not None:
            self._save_button.setText("儲存" if self.lang == "CHN" else "Save")
        if getattr(self, "_cancel_button", None) is not None:
            self._cancel_button.setText("取消" if self.lang == "CHN" else "Cancel")

    def refresh_data_formats_from_dict(self) -> None:
        """資料字典重新載入後，依 DATA_TYPE 重設表單顯示與 TX Grid。"""
        for field, w in self._editors.items():
            f_fmt = self.data_dict.get_data_format(self.table_name, field)
            f_typ = self.data_dict.get_data_type(self.table_name, field)
            if isinstance(w, QLineEdit):
                raw = normalize_storage_value(field, f_fmt, w.text(), f_typ)
                _init_form_editor_value(w, field, raw, f_fmt, f_typ)
            elif isinstance(w, QDateEdit):
                d = w.date()
                w.setDisplayFormat(APP_DATE_QT_FORMAT)
                if d.isValid():
                    w.setDate(d)
            elif isinstance(w, QTextEdit):
                raw = normalize_storage_value(field, f_fmt, w.toPlainText(), f_typ)
                _init_form_editor_value(w, field, raw, f_fmt, f_typ)
        for pane in self._tx_tables.values():
            pane.refresh_data_cells()

    def _open_lookup(self, field: str, lookup_db: str, lookup_ret: str) -> None:
        if not self.backend:
            return
        from ui.lookup_dialog import LookupPickerDialog

        dlg = LookupPickerDialog(
            lookup_db=lookup_db,
            lookup_ret=lookup_ret,
            backend=self.backend,
            data_dict=self.data_dict,
            lang=self.lang,
            parent=self,
            app_base_dir=getattr(self, "_app_base_dir", None),
        )
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        w = self._editors.get(field)
        if accepted:
            val = (dlg.selected_value or "").strip()
            if val and isinstance(w, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
                f_fmt = self.data_dict.get_data_format(self.table_name, field)
                f_typ = self.data_dict.get_data_type(self.table_name, field)
                _init_form_editor_value(w, field, val, f_fmt, f_typ)
                apply_form_field_search_ret(
                    host=self,
                    data_dict=self.data_dict,
                    backend=self.backend,
                    table_name=self.table_name,
                    field=field,
                    editors=self._editors,
                    lang=self.lang,
                )
        # LOOKUP 關閉後焦點回到輸入欄
        if isinstance(w, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
            _activate_form_tab_for_widget(
                getattr(self, "_form_tab_widget", None), w
            )
            _focus_form_widget(w)

    def _refresh_layout_toggle_button(self) -> None:
        btn = getattr(self, "_layout_toggle_button", None)
        if btn is None:
            return
        planned = self._form_layout_mode == FORM_LAYOUT_PLANNED
        if self.lang == "CHN":
            btn.setText("預設介面" if planned else "規劃介面")
            btn.setToolTip(
                "切換為左標右欄預設輸入介面"
                if planned
                else "切換為上標下欄規劃輸入介面（3×5／5×5）"
            )
        else:
            btn.setText("Default UI" if planned else "Planned UI")
            btn.setToolTip(
                "Switch to default left-label form layout"
                if planned
                else "Switch to planned top-label form layout (3×5 / 5×5)"
            )
        apply_work_action_button_style(btn)

    def _rebuild_form_tabs(self) -> None:
        if self._form_tab_widget is None or not getattr(self, "_field_meta", None):
            return
        _apply_form_label_widths_for_mode(
            self._labels,
            {
                f: self.data_dict.get_title(self.table_name, f, self.lang)
                for f in self.field_names
            },
            base_dir=self._app_base_dir,
            layout_mode=self._form_layout_mode,
        )
        for ed in self._editors.values():
            _apply_form_editor_dimensions(ed, self._form_layout_mode)
        self._form_tab_keys = _populate_form_tab_widget(
            self._form_tab_widget,
            self._field_meta,
            table_name=self.table_name,
            data_dict=self.data_dict,
            layout_mode=self._form_layout_mode,
            labels_by_field=self._labels,
            tab_title_fn=self._form_tab_title_by_key,
        )

    def _toggle_form_layout_mode(self) -> None:
        nxt = (
            FORM_LAYOUT_DEFAULT
            if self._form_layout_mode == FORM_LAYOUT_PLANNED
            else FORM_LAYOUT_PLANNED
        )
        self._form_layout_mode = set_form_layout_mode(nxt, self._app_base_dir)
        self._refresh_layout_toggle_button()
        self._rebuild_form_tabs()
        if hasattr(self, "_refresh_arap_vou_locks"):
            self._refresh_arap_vou_locks()

    def _get_editor_values(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for field in self.field_names:
            w = self._editors.get(field)
            f_fmt = self.data_dict.get_data_format(self.table_name, field)
            f_typ = self.data_dict.get_data_type(self.table_name, field)
            if isinstance(w, QComboBox):
                txt = (w.currentText() or "").strip()
                out[field] = normalize_storage_value(field, f_fmt, txt, f_typ)
            elif isinstance(w, QLineEdit):
                txt = w.text().strip()
                out[field] = normalize_storage_value(field, f_fmt, txt, f_typ)
            elif isinstance(w, QDateEdit):
                out[field] = w.date().toString(APP_DATE_QT_FORMAT)
            elif isinstance(w, QTextEdit):
                txt = w.toPlainText().strip()
                out[field] = normalize_storage_value(field, f_fmt, txt, f_typ)
            else:
                out[field] = ""
        return out

    def _do_save(self) -> None:
        vals = self._get_editor_values()
        if self.on_save and self.on_save(vals, self.is_new):
            for pane in self._tx_tables.values():
                if not pane.save_to_backend():
                    msg = "交易明細儲存失敗。"
                    if pane.last_error:
                        msg = f"{msg}\n\nDetail: {pane.last_error}"
                    QMessageBox.warning(self, "儲存失敗", msg)
                    return
            self.accept()
        elif self.on_save:
            err = ""
            if self.backend is not None:
                err = str(getattr(self.backend, "last_error", "") or "").strip()
            msg = "無法寫入資料，請檢查後再試。"
            if err:
                msg = f"{msg}\n\nDetail: {err}"
            QMessageBox.warning(self, "儲存失敗", msg)


class RecordDetailPage(QWidget):
    """
    右側分頁明細：主檔動態表單 + TX_FILE 多 Grid（供輸入），儲存/取消。
    """

    def __init__(
        self,
        table_name: str,
        field_names: List[str],
        values: Dict[str, str],
        old_row: List[str],
        data_dict: DataDictionary,
        lang: LanguageCode,
        backend: Optional["DbBackendBase"] = None,
        tx_files: Optional[List[str]] = None,
        on_saved: Optional[Callable[..., None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        title: str = "",
        menu_item_title: str = "",
        physical_field_names: Optional[List[str]] = None,
        key_filter_column: Optional[str] = None,
        app_base_dir: Optional[str] = None,
        work_actions: Optional[WorkActionFlags] = None,
        do_proc: str = "",
        company_co_key: str = "",
        print_doc_key_column: Optional[str] = None,
        number_config: Optional[ProgramNumberConfig] = None,
        tx_source_row: Optional[List[str]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._app_base_dir = (
            os.path.abspath(app_base_dir)
            if app_base_dir
            else os.path.dirname(os.path.abspath(data_dict.mdb_path))
        )
        if self._app_base_dir:
            load_ui_font_settings(self._app_base_dir)
        self.table_name = table_name
        self.field_names = field_names
        self.physical_fields = list(physical_field_names or field_names)
        self.values = dict(values)
        self._old_row = list(old_row)
        self.data_dict = data_dict
        self.lang = lang
        self.backend = backend
        self.tx_files = tx_files or []
        self.on_saved = on_saved or (lambda *_a, **_k: None)
        self.on_close = on_close or (lambda: None)
        self._page_title = title or table_name
        self._menu_item_title = (menu_item_title or "").strip()
        self._form_tab_widget: Optional[QTabWidget] = None
        self._form_tab_keys: List[str] = []
        self._work_actions = work_actions or WorkActionFlags()
        self._do_proc = (do_proc or "").strip()
        self._company_co_key = (company_co_key or "").strip()
        self._print_doc_key_column = (print_doc_key_column or key_filter_column or "").strip()
        self._number_config = number_config
        self._tx_source_row = list(tx_source_row or [])
        self._source_tx_key: Optional[str] = None
        if self._tx_source_row and self._is_new_record():
            _, self._source_tx_key = _master_key_from_physical_row(
                self.physical_fields,
                self._tx_source_row,
                key_column=(print_doc_key_column or key_filter_column or "").strip(),
            )
        self._tx_key_column = (key_filter_column or "").strip()
        self._master_tx_key: Optional[str] = None
        if self._tx_key_column:
            for f in self.field_names:
                if f.strip().upper() == self._tx_key_column.upper():
                    v = (self.values.get(f) or "").strip()
                    self._master_tx_key = v or None
                    break
        if not self._master_tx_key:
            self._tx_key_column = "TX_KEY"
            for f in self.field_names:
                if f.strip().upper() == "TX_KEY":
                    v = (self.values.get(f) or "").strip()
                    self._master_tx_key = v or None
                    break

        self._editors: Dict[str, QWidget] = {}
        self._labels: Dict[str, QLabel] = {}
        self._tx_tables: Dict[str, TxDetailGridPane] = {}
        self._field_meta: List[Dict[str, object]] = []
        self._form_layout_mode = get_form_layout_mode(self._app_base_dir)

        self._build_ui()
        self._install_form_field_navigation()
        self._install_search_ret_hooks()
        self._install_arap_vou_locks()

    def _reapply_detail_grids(self) -> None:
        for pane in self._tx_tables.values():
            reapply_grid_fonts(pane.table, self._app_base_dir)

    def _arap_proc_name(self) -> str:
        return ""

    def _arap_do_proc(self) -> str:
        return (getattr(self, "_do_proc", None) or "") or ""

    def _refresh_arap_vou_locks(self) -> None:
        _refresh_form_arap_vou_locks(
            field_meta=getattr(self, "_field_meta", []) or [],
            editors=getattr(self, "_editors", {}) or {},
            data_dict=self.data_dict,
            table_name=self.table_name,
            is_new_record=self._is_new_record(),
            base_dir=getattr(self, "_app_base_dir", None),
            proc_name=self._arap_proc_name(),
            do_proc=self._arap_do_proc(),
        )

    def _install_arap_vou_locks(self) -> None:
        _install_arap_vou_type_lock_hooks(
            getattr(self, "_editors", {}) or {},
            proc_name=self._arap_proc_name(),
            do_proc=self._arap_do_proc(),
            on_change=self._refresh_arap_vou_locks,
        )

    def _reapply_detail_form(self) -> None:
        reapply_form_fonts(
            self._labels,
            self._editors,
            base_dir=self._app_base_dir,
            table_name=self.table_name,
            data_dict=self.data_dict,
            field_names=self.field_names,
            lang=self.lang,
        )
        self._refresh_arap_vou_locks()

    def reapply_detail_theme(self) -> None:
        """主題切換後重套明細表單標題、按鈕與 TX Grid。"""
        self._reapply_detail_grids()
        self._reapply_detail_form()
        for btn in (
            getattr(self, "_layout_toggle_button", None),
            getattr(self, "_attach_button", None),
            getattr(self, "_save_button", None),
            getattr(self, "_cancel_button", None),
        ):
            if btn is not None:
                apply_work_action_button_style(btn)
        for pane in self._tx_tables.values():
            pane.reapply_theme_styles()
        for m in self._field_meta:
            display = m.get("display")
            if isinstance(display, QWidget):
                for btn in display.findChildren(QPushButton):
                    btn.setStyleSheet(lookup_button_qss())

    def _menu_base_title(self) -> str:
        base = (self._menu_item_title or "").strip()
        if base:
            return base
        if "—" in self._page_title:
            return self._page_title.split("—", 1)[0].strip()
        return self.data_dict.get_title(self.table_name, self.table_name, self.lang)

    def _form_tab_title(self, idx1: int, total_tabs: int = 1) -> str:
        base = self._menu_base_title()
        if self.lang == "CHN":
            if total_tabs <= 1:
                return f"{base} 資 料"
            return f"{base} 資 料 - {idx1}"
        if total_tabs <= 1:
            return f"{base} Data"
        return f"{base} Data - {idx1}"

    def _form_tab_title_by_key(self, tab_key: str, idx1: int, total_tabs: int) -> str:
        return _form_tab_title_for_key(
            tab_key,
            idx1,
            total_tabs,
            lang=self.lang,
            menu_base=self._menu_base_title(),
        )

    def _detail_tab_title(self, idx1: int, total_tabs: int = 1) -> str:
        base = self._menu_base_title()
        if self.lang == "CHN":
            if total_tabs <= 1:
                return f"{base} 明 細"
            return f"{base} 明 細 - {idx1}"
        if total_tabs <= 1:
            return f"{base} Detail"
        return f"{base} Detail - {idx1}"

    def _install_search_ret_hooks(self) -> None:
        install_form_search_ret_hooks(
            self,
            data_dict=self.data_dict,
            backend=self.backend,
            table_name=self.table_name,
            field_names=self.field_names,
            editors=self._editors,
            lang=self.lang,
        )

    def _install_form_field_navigation(self) -> None:
        """QLineEdit / QDateEdit / QTextEdit：Enter／下鍵 → 下一欄；上鍵 → 上一欄。"""
        self._line_edit_order = []
        self._line_edit_field = {}
        self._form_nav_widgets = set()
        self._form_nav_proxy: Dict[QWidget, QWidget] = {}
        for f in self.field_names:
            ed = self._editors.get(f)
            if isinstance(ed, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
                if isinstance(ed, QLineEdit):
                    self._line_edit_field[ed] = f
                    self._line_edit_order.append(ed)
                self._form_nav_widgets.add(ed)
                try:
                    ed.installEventFilter(self)
                except Exception:
                    pass
                _form_bind_composite_nav_proxy(self, ed, self._form_nav_proxy)
        QTimer.singleShot(0, self._rebind_form_composite_nav_proxy)

    def _rebind_form_composite_nav_proxy(self) -> None:
        proxy = getattr(self, "_form_nav_proxy", None)
        if not isinstance(proxy, dict):
            return
        for ed in getattr(self, "_form_nav_widgets", set()) or set():
            _form_bind_composite_nav_proxy(self, ed, proxy)

    def eventFilter(self, obj, event) -> bool:
        nav_widgets = getattr(self, "_form_nav_widgets", set())
        proxy = getattr(self, "_form_nav_proxy", {})
        if event.type() == QEvent.Type.FocusIn:
            host_ed = _form_resolve_nav_editor(obj, nav_widgets, proxy)
            if host_ed is not None:
                _form_bind_composite_nav_proxy(self, host_ed, proxy)
        nav_obj = _form_resolve_nav_editor(obj, nav_widgets, proxy)
        if (
            event.type() == QEvent.Type.KeyPress
            and isinstance(nav_obj, (QLineEdit, QDateEdit, QTextEdit, QComboBox))
        ):
            key = event.key()
            if key in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Down,
                Qt.Key.Key_Right,
            ):
                field = getattr(self, "_line_edit_field", {}).get(nav_obj) if isinstance(nav_obj, QLineEdit) else None
                if field is None:
                    for f, ed in self._editors.items():
                        if ed is nav_obj:
                            field = f
                            break
                if field and not apply_form_field_search_ret(
                    host=self,
                    data_dict=self.data_dict,
                    backend=self.backend,
                    table_name=self.table_name,
                    field=field,
                    editors=self._editors,
                    lang=self.lang,
                ):
                    return True
            if _handle_form_field_key_nav(
                self.field_names,
                self._editors,
                nav_widgets,
                nav_obj,
                event,
                getattr(self, "_tx_tab_widget", None),
                getattr(self, "_save_button", None),
                getattr(self, "_form_tab_widget", None),
            ):
                return True
        return super().eventFilter(obj, event)

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setChildrenCollapsible(False)

        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(4, 4, 4, 4)
        form_layout.setSpacing(4)

        field_meta: List[Dict[str, object]] = []
        for field in self.field_names:
            title = self.data_dict.get_title(self.table_name, field, self.lang)
            label = QLabel(_form_label_caption(title))
            label.setStyleSheet(form_label_style(self._app_base_dir))
            label.setAlignment(_form_label_align_vcenter())
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._labels[field] = label

            f_fmt = self.data_dict.get_data_format(self.table_name, field)
            f_typ = self.data_dict.get_data_type(self.table_name, field)
            is_long = _is_long_text_field(field, f_typ)
            combo_choices = self.data_dict.get_combo_choices(self.table_name, field)
            use_combo = self.data_dict.field_uses_combo(self.table_name, field)
            editor = _create_form_editor(
                field,
                f_fmt,
                f_typ,
                combo_choices=combo_choices,
                use_combo=use_combo,
            )
            editor.setStyleSheet(form_editor_style(self._app_base_dir))
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            _apply_form_editor_dimensions(editor, self._form_layout_mode)
            _disable_ime(editor)
            _init_form_editor_value(
                editor, field, self.values.get(field, ""), f_fmt, f_typ
            )
            self._editors[field] = editor

            display: QWidget = editor
            lookup_db, lookup_key, lookup_ret = self.data_dict.get_lookup(
                self.table_name, field
            )
            if (lookup_key or "").strip() and (lookup_db or "").strip():
                display = _wrap_lookup_field_editor(
                    editor,
                    on_lookup=lambda *_a, f=field, db=lookup_db, ret=lookup_ret: self._open_lookup(
                        f, db, ret
                    ),
                    lang=self.lang,
                )
            apply_form_field_edit_state(
                field,
                editor,
                display,
                data_dict=self.data_dict,
                table_name=self.table_name,
                is_new_record=self._is_new_record(),
                base_dir=self._app_base_dir,
            )

            field_meta.append(
                {
                    "field": field,
                    "label": label,
                    "editor": editor,
                    "display": display,
                    "is_long": is_long,
                }
            )

        self._field_meta = field_meta
        _apply_form_label_widths_for_mode(
            self._labels,
            {
                f: self.data_dict.get_title(self.table_name, f, self.lang)
                for f in self.field_names
            },
            base_dir=self._app_base_dir,
            layout_mode=self._form_layout_mode,
        )

        tab_widget = QTabWidget()
        self._form_tab_widget = tab_widget
        self._form_tab_keys = _populate_form_tab_widget(
            tab_widget,
            self._field_meta,
            table_name=self.table_name,
            data_dict=self.data_dict,
            layout_mode=self._form_layout_mode,
            labels_by_field=self._labels,
            tab_title_fn=self._form_tab_title_by_key,
        )
        form_layout.addWidget(tab_widget)

        scroll.setWidget(form_container)
        top_layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        self._layout_toggle_button = QPushButton()
        apply_work_action_button_style(self._layout_toggle_button)
        self._layout_toggle_button.clicked.connect(self._toggle_form_layout_mode)
        self._refresh_layout_toggle_button()
        self._attach_button: Optional[QPushButton] = None
        if bool(getattr(self._work_actions, "need_attach", False)):
            attach_label = "附件" if self.lang == "CHN" else "Attachment"
            btn_attach = QPushButton(attach_label)
            btn_attach.setIcon(icon_from_key(self.style(), "attachment"))
            apply_work_action_button_style(btn_attach)
            btn_attach.clicked.connect(self._on_detail_attachment)
            self._attach_button = btn_attach
        btn_save = QPushButton("儲存" if self.lang == "CHN" else "Save")
        btn_save.setIcon(icon_from_key(self.style(), "save"))
        apply_work_action_button_style(btn_save)
        btn_cancel = QPushButton("取消" if self.lang == "CHN" else "Cancel")
        btn_cancel.setIcon(icon_from_key(self.style(), "cancel"))
        apply_work_action_button_style(btn_cancel)
        btn_save.clicked.connect(self._do_save)
        btn_cancel.clicked.connect(self._do_cancel)
        btn_row.addWidget(self._layout_toggle_button)
        btn_row.addStretch(1)
        if self._attach_button is not None:
            btn_row.addWidget(self._attach_button)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch(1)
        self._save_button = btn_save
        self._cancel_button = btn_cancel
        top_layout.addLayout(btn_row)

        splitter.addWidget(top_panel)

        if self.tx_files:
            tabs = QTabWidget()
            for tx_name in self.tx_files:
                pane = TxDetailGridPane(
                    tx_name,
                    self.data_dict,
                    self.lang,
                    self.backend,
                    self._master_tx_key,
                    master_filter_column=self._tx_key_column,
                    source_tx_key=self._source_tx_key,
                    parent=self,
                )
                self._tx_tables[tx_name] = pane
                tabs.addTab(pane, tx_name)
            tx_tab_count = tabs.count()
            for i in range(tx_tab_count):
                tabs.setTabText(i, self._detail_tab_title(i + 1, tx_tab_count))
            from core.ui_theme import apply_tab_title_colors

            apply_tab_title_colors(tabs)
            self._tx_tab_widget = tabs
            splitter.addWidget(tabs)
        else:
            # 無 TX_FILE：下方空白仍佔 40%，表單區佔 60%
            self._tx_tab_widget = None
            bottom_placeholder = QWidget()
            bottom_placeholder.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            splitter.addWidget(bottom_placeholder)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 400])
        main_layout.addWidget(splitter, 1)

    def _refresh_layout_toggle_button(self) -> None:
        btn = getattr(self, "_layout_toggle_button", None)
        if btn is None:
            return
        planned = self._form_layout_mode == FORM_LAYOUT_PLANNED
        if self.lang == "CHN":
            btn.setText("預設介面" if planned else "規劃介面")
            btn.setToolTip(
                "切換為左標右欄預設輸入介面"
                if planned
                else "切換為上標下欄規劃輸入介面（3×5／5×5）"
            )
        else:
            btn.setText("Default UI" if planned else "Planned UI")
            btn.setToolTip(
                "Switch to default left-label form layout"
                if planned
                else "Switch to planned top-label form layout (3×5 / 5×5)"
            )
        apply_work_action_button_style(btn)

    def _rebuild_form_tabs(self) -> None:
        if self._form_tab_widget is None or not self._field_meta:
            return
        _apply_form_label_widths_for_mode(
            self._labels,
            {
                f: self.data_dict.get_title(self.table_name, f, self.lang)
                for f in self.field_names
            },
            base_dir=self._app_base_dir,
            layout_mode=self._form_layout_mode,
        )
        for ed in self._editors.values():
            _apply_form_editor_dimensions(ed, self._form_layout_mode)
        self._form_tab_keys = _populate_form_tab_widget(
            self._form_tab_widget,
            self._field_meta,
            table_name=self.table_name,
            data_dict=self.data_dict,
            layout_mode=self._form_layout_mode,
            labels_by_field=self._labels,
            tab_title_fn=self._form_tab_title_by_key,
        )

    def _toggle_form_layout_mode(self) -> None:
        nxt = (
            FORM_LAYOUT_DEFAULT
            if self._form_layout_mode == FORM_LAYOUT_PLANNED
            else FORM_LAYOUT_PLANNED
        )
        self._form_layout_mode = set_form_layout_mode(nxt, self._app_base_dir)
        self._refresh_layout_toggle_button()
        self._rebuild_form_tabs()
        if hasattr(self, "_refresh_arap_vou_locks"):
            self._refresh_arap_vou_locks()

    def set_language(self, lang: LanguageCode) -> None:
        self.lang = lang
        if self._form_tab_widget is not None:
            form_tab_count = self._form_tab_widget.count()
            for i in range(form_tab_count):
                key = self._form_tab_keys[i] if i < len(self._form_tab_keys) else ""
                self._form_tab_widget.setTabText(
                    i, self._form_tab_title_by_key(key, i + 1, form_tab_count)
                )
        if getattr(self, "_tx_tab_widget", None) is not None:
            tx_tab_count = self._tx_tab_widget.count()
            for i in range(tx_tab_count):
                self._tx_tab_widget.setTabText(i, self._detail_tab_title(i + 1, tx_tab_count))
            from core.ui_theme import apply_tab_title_colors

            apply_tab_title_colors(self._tx_tab_widget)
        if self._form_tab_widget is not None:
            from core.ui_theme import apply_tab_title_colors

            apply_tab_title_colors(self._form_tab_widget)
        for field, label in self._labels.items():
            label.setText(
                _form_label_caption(
                    self.data_dict.get_title(self.table_name, field, self.lang)
                )
            )
        for pane in self._tx_tables.values():
            pane.set_language(self.lang)
        if getattr(self, "_save_button", None) is not None:
            self._save_button.setText("儲存" if self.lang == "CHN" else "Save")
            apply_work_action_button_style(self._save_button)
        if getattr(self, "_cancel_button", None) is not None:
            self._cancel_button.setText("取消" if self.lang == "CHN" else "Cancel")
            apply_work_action_button_style(self._cancel_button)
        self._refresh_layout_toggle_button()

    def refresh_after_data_dictionary_reload(self) -> None:
        """資料字典重新載入後，依 DATA_TYPE 重設表單顯示與 TX Grid。"""
        self.data_dict.reload_columns_for_table(self.table_name)
        for field, label in self._labels.items():
            label.setText(
                _form_label_caption(
                    self.data_dict.get_title(self.table_name, field, self.lang)
                )
            )
        for field, w in self._editors.items():
            f_fmt = self.data_dict.get_data_format(self.table_name, field)
            f_typ = self.data_dict.get_data_type(self.table_name, field)
            if isinstance(w, QLineEdit):
                raw = normalize_storage_value(field, f_fmt, w.text(), f_typ)
                _init_form_editor_value(w, field, raw, f_fmt, f_typ)
            elif isinstance(w, QDateEdit):
                d = w.date()
                w.setDisplayFormat(APP_DATE_QT_FORMAT)
                if d.isValid():
                    w.setDate(d)
            elif isinstance(w, QTextEdit):
                raw = normalize_storage_value(field, f_fmt, w.toPlainText(), f_typ)
                _init_form_editor_value(w, field, raw, f_fmt, f_typ)
        for pane in self._tx_tables.values():
            pane.refresh_data_cells()

    def _open_lookup(self, field: str, lookup_db: str, lookup_ret: str) -> None:
        """LOOKUP_KEY：開啟 LOOKUP_DB Grid，選取 LOOKUP_RET 寫回輸入欄。"""
        if not self.backend:
            return
        from ui.lookup_dialog import LookupPickerDialog

        dlg = LookupPickerDialog(
            lookup_db=lookup_db,
            lookup_ret=lookup_ret,
            backend=self.backend,
            data_dict=self.data_dict,
            lang=self.lang,
            parent=self,
            app_base_dir=getattr(self, "_app_base_dir", None),
        )
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        w = self._editors.get(field)
        if accepted:
            val = (dlg.selected_value or "").strip()
            if val and isinstance(w, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
                f_fmt = self.data_dict.get_data_format(self.table_name, field)
                f_typ = self.data_dict.get_data_type(self.table_name, field)
                _init_form_editor_value(w, field, val, f_fmt, f_typ)
                apply_form_field_search_ret(
                    host=self,
                    data_dict=self.data_dict,
                    backend=self.backend,
                    table_name=self.table_name,
                    field=field,
                    editors=self._editors,
                    lang=self.lang,
                )
        # LOOKUP 關閉後焦點回到輸入欄
        if isinstance(w, (QLineEdit, QDateEdit, QTextEdit, QComboBox)):
            _activate_form_tab_for_widget(
                getattr(self, "_form_tab_widget", None), w
            )
            _focus_form_widget(w)

    def _get_editor_values(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for field in self.field_names:
            w = self._editors.get(field)
            f_fmt = self.data_dict.get_data_format(self.table_name, field)
            f_typ = self.data_dict.get_data_type(self.table_name, field)
            if isinstance(w, QComboBox):
                txt = (w.currentText() or "").strip()
                out[field] = normalize_storage_value(field, f_fmt, txt, f_typ)
            elif isinstance(w, QLineEdit):
                txt = w.text().strip()
                out[field] = normalize_storage_value(field, f_fmt, txt, f_typ)
            elif isinstance(w, QDateEdit):
                out[field] = w.date().toString(APP_DATE_QT_FORMAT)
            elif isinstance(w, QTextEdit):
                txt = w.toPlainText().strip()
                out[field] = normalize_storage_value(field, f_fmt, txt, f_typ)
            else:
                out[field] = ""
        return out

    def _resolve_update_where(self) -> tuple[List[str], List[str]]:
        """優先用穩定鍵欄位更新，避免因顯示格式/空白差異造成 WHERE 比對不到。"""
        return resolve_update_where(
            self.physical_fields,
            self._old_row,
            print_doc_key_column=self._print_doc_key_column or self._tx_key_column,
            form_fields=self.field_names,
        )

    def _on_detail_attachment(self) -> None:
        """對齊主作業 NEED_ATTACH：依目前表單／舊列解析附件。"""
        from core.attachment_messages import format_attach_not_found_message
        from core.attachment_service import resolve_attachments_for_row
        from ui.attachment_dialog import open_attachments
        from ui.message_dialog import show_copyable_message

        vals = self._get_editor_values()
        row: List[str] = []
        for i, f in enumerate(self.physical_fields):
            v = vals.get(f)
            if v is None or not str(v).strip():
                # 以欄位名稱大小寫不敏感找表單值
                found = ""
                fu = f.strip().upper()
                for k, kv in vals.items():
                    if str(k).strip().upper() == fu:
                        found = str(kv or "")
                        break
                if found.strip():
                    row.append(found)
                elif i < len(self._old_row):
                    row.append(str(self._old_row[i] or ""))
                else:
                    row.append("")
            else:
                row.append(str(v))

        lookup_col, key_value, folder, files = resolve_attachments_for_row(
            self._work_actions.attach_path,
            self._work_actions.attach_key,
            self._print_doc_key_column or "",
            self.physical_fields,
            row,
            co_key=self._company_co_key,
            do_proc=self._do_proc,
            table_name=self.table_name,
            app_base_dir=self._app_base_dir
            or os.path.dirname(os.path.abspath(self.data_dict.mdb_path)),
        )
        chn = self.lang == "CHN"
        title = "附件" if chn else "Attachment"
        if not lookup_col:
            show_copyable_message(
                self,
                title,
                (
                    "未設定 ATTACH_KEY 或 KEY_CODE 欄位。"
                    if chn
                    else "ATTACH_KEY or KEY_CODE column is not configured."
                ),
            )
            return
        if not key_value:
            show_copyable_message(
                self,
                title,
                (
                    f"目前記錄的「{lookup_col}」為空白，無法搜尋附件。"
                    if chn
                    else f'Field "{lookup_col}" is empty; cannot search attachments.'
                ),
            )
            return
        if not files:
            show_copyable_message(
                self,
                title,
                format_attach_not_found_message(
                    self.lang,
                    key_value,
                    folder,
                    getattr(self, "_group_level", None),
                    folder_missing=bool(folder) and not os.path.isdir(folder),
                ),
            )
            return
        open_attachments(files, lang=self.lang, parent=self)

    def _sync_tx_master_key_from_values(self, vals: Dict[str, str]) -> None:
        """儲存前依表單主鍵更新 TX pane 的過濾鍵（新增／複製填入鍵後需同步）。"""
        key_col = (self._tx_key_column or "").strip()
        key_val = ""
        if key_col:
            for f, v in (vals or {}).items():
                if str(f).strip().upper() == key_col.upper():
                    key_val = str(v or "").strip()
                    break
        if not key_val:
            for f, v in (vals or {}).items():
                if str(f).strip().upper() == "TX_KEY":
                    key_col = str(f)
                    key_val = str(v or "").strip()
                    break
        if key_col:
            self._tx_key_column = key_col
        self._master_tx_key = key_val or None
        for pane in self._tx_tables.values():
            pane._master_tx_key = self._master_tx_key
            if key_col:
                pane._master_filter_column = key_col.strip().upper()

    def _is_new_record(self) -> bool:
        return not any(str(x or "").strip() for x in (self._old_row or []))

    def _prepare_save_values(self, vals: Dict[str, str]) -> Optional[Dict[str, str]]:
        """新增／複製儲存前依 PROGRAM 編號規則準備鍵值；取消手動編號時回傳 None。"""
        if not self._is_new_record():
            return vals
        if self.backend is None or self._number_config is None:
            return vals
        try:
            return prepare_record_key_values(
                self.backend,
                self.table_name,
                self.physical_fields,
                self._number_config,
                vals,
                is_new=True,
            )
        except ManualKeyRequired as ex:
            label = self.data_dict.get_title(
                self.table_name, ex.key_field, self.lang
            )
            lookup_db, _lookup_key, lookup_ret = self.data_dict.get_lookup(
                self.table_name, ex.key_field
            )
            # COLUMNS 無 LOOKUP_DB 時：顯示本作業 DBF_NAME（WORK_FILE）GRID，選 KEY_CODE 欄
            if not (lookup_db or "").strip():
                lookup_db = self.table_name
            if not (lookup_ret or "").strip():
                lookup_ret = ex.key_field
            dlg = KeyAssignDialog(
                key_field=ex.key_field,
                key_label=label or ex.key_field,
                suggested_key=ex.suggested_key,
                lang=self.lang,
                parent=self,
                backend=self.backend,
                data_dict=self.data_dict,
                table_name=self.table_name,
                lookup_db=lookup_db,
                lookup_ret=lookup_ret,
                app_base_dir=getattr(self, "_app_base_dir", None),
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return None
            try:
                return prepare_record_key_values(
                    self.backend,
                    self.table_name,
                    self.physical_fields,
                    self._number_config,
                    vals,
                    is_new=True,
                    manual_key=dlg.assigned_key(),
                )
            except ValueError as err:
                QMessageBox.warning(
                    self,
                    "錯誤" if self.lang == "CHN" else "Error",
                    str(err) or ("編號重複或無效。" if self.lang == "CHN" else "Duplicate or invalid key."),
                )
                return None
        except ValueError as err:
            QMessageBox.warning(
                self,
                "錯誤" if self.lang == "CHN" else "Error",
                str(err) or ("編號重複或無效。" if self.lang == "CHN" else "Duplicate or invalid key."),
            )
            return None

    def _do_save(self) -> None:
        vals = self._get_editor_values()
        prepared = self._prepare_save_values(vals)
        if prepared is None:
            return
        vals = prepared
        _apply_form_values_to_editors(
            self._editors,
            self.field_names,
            vals,
            self.table_name,
            self.data_dict,
        )
        new_list = [vals.get(f, "") for f in self.field_names]
        is_new = self._is_new_record()
        ok = False
        if self.backend is None:
            ok = False
        elif is_new:
            ins_fields = list(self.field_names)
            ins_values = list(new_list)
            if self._number_config is not None and self._number_config.auto_numbering:
                ins_fields, ins_values = merge_allocated_key_fields(
                    ins_fields,
                    ins_values,
                    self._number_config,
                    vals,
                    self.physical_fields,
                )
            ins_fields, ins_values = apply_insert_bit_defaults(
                self.physical_fields,
                ins_fields,
                ins_values,
                is_boolean_column=lambda f: is_boolean_data_type(
                    self.data_dict.get_data_type(self.table_name, f)
                ),
            )
            ok = bool(
                self.backend.insert_one(self.table_name, ins_fields, ins_values)
            )
        else:
            where_fields, old_where_vals = self._resolve_update_where()
            ok = bool(
                self.backend.update_one(
                    self.table_name,
                    self.field_names,
                    new_list,
                    where_fields,
                    old_where_vals,
                )
            )
        if ok:
            self._sync_tx_master_key_from_values(vals)
            for pane in self._tx_tables.values():
                if not pane.save_to_backend():
                    msg = (
                        "主檔已儲存，但交易明細儲存失敗。"
                        if self.lang == "CHN"
                        else "Header saved, but transaction detail save failed."
                    )
                    if pane.last_error:
                        msg = f"{msg}\n\nDetail: {pane.last_error}"
                    QMessageBox.warning(self, "錯誤" if self.lang == "CHN" else "Error", msg)
                    return
            if is_new:
                # 建立完整 old_row 供後續若仍留在頁面可改為 update
                self._old_row = []
                for f in self.physical_fields:
                    found = ""
                    fu = str(f).strip().upper()
                    for k, kv in vals.items():
                        if str(k).strip().upper() == fu:
                            found = str(kv or "")
                            break
                    self._old_row.append(found)
            else:
                for i, fname in enumerate(self.physical_fields):
                    if fname in vals and i < len(self._old_row):
                        self._old_row[i] = vals[fname]
            # 新增／複製：傳入新列定位；更改：傳入更新後列
            try:
                self.on_saved(list(self._old_row))
            except TypeError:
                self.on_saved()
            # NUM_CONTROL 或 NUM_TYPE 非空白（自動編號）：儲存後顯示所產生的編號
            if is_new and self._number_config is not None and self._number_config.auto_numbering:
                key_field = (self._number_config.key_field or "").strip()
                key_val = ""
                if key_field:
                    for f, v in vals.items():
                        if str(f).strip().upper() == key_field.upper():
                            key_val = str(v or "").strip()
                            break
                if key_val:
                    key_label = self.data_dict.get_title(
                        self.table_name, key_field, self.lang
                    ) or key_field
                    QMessageBox.information(
                        self,
                        "儲存成功" if self.lang == "CHN" else "Saved",
                        (
                            f"編號已儲存：{key_label} = {key_val}"
                            if self.lang == "CHN"
                            else f"Saved number: {key_label} = {key_val}"
                        ),
                    )
            self.on_close()
        else:
            err = ""
            if self.backend is not None:
                err = str(getattr(self.backend, "last_error", "") or "").strip()
            msg = "儲存失敗。" if self.lang == "CHN" else "Save failed."
            if err:
                msg = f"{msg}\n\nDetail: {err}"
            QMessageBox.warning(
                self,
                "錯誤" if self.lang == "CHN" else "Error",
                msg,
            )

    def _do_cancel(self) -> None:
        self.on_close()


