# src/artist_field.py
"""
Artist input with:
  * autocomplete per artist (works after "&", ",", "en", "feat." too),
    accent/case-insensitive, most used artists first
  * a picker dialog (list button at the right of the field) to tick one or more known artists
  * a hint line under the field: "Suggestion: … [Apply]" (also fixes typos) or
    "Not in list: … [Add to list] [Add as AKV]"
  * ArtistDelegate: the same autocomplete inside a table cell (web matcher)
"""

import re

from PyQt6.QtCore import Qt, QStringListModel, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QCompleter, QLabel, QPushButton, QDialog,
                             QListWidget, QListWidgetItem, QDialogButtonBox,
                             QCheckBox, QMenu, QStyledItemDelegate)

from artist_catalog import split_artists, normalize_key, TAG_AKV
from app_translations import tr

# Separators after which a new artist starts (for autocomplete)
_SEGMENT_SPLIT = re.compile(r"(.*(?:,|;|&|\+|\s(?:en|ft\.?|feat\.?|featuring)\s))\s*",
                            re.IGNORECASE)


def _split_current_segment(text):
    """'Den Bremt & ga' -> ('Den Bremt & ', 'ga')"""
    m = _SEGMENT_SPLIT.match(text)
    if not m:
        return "", text
    head = m.group(1)
    if not head.endswith(" "):
        head += " "
    return head, text[m.end():]


def _list_icon():
    """Small 'list' icon drawn in code (no image files needed)."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#96CBD0"), 3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for y in (9, 16, 23):
        p.drawPoint(6, y)
        p.drawLine(12, y, 27, y)
    p.end()
    return QIcon(pm)


class ArtistLineEdit(QLineEdit):
    """A QLineEdit (so the main window can treat it like the other fields)."""

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setMinimumHeight(30)

        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setMaxVisibleItems(12)
        self._completer.activated[str].connect(self._insert_completion)
        self.textEdited.connect(self._update_completions)

        self.picker_action = QAction(_list_icon(), "", self)
        self.picker_action.setToolTip(tr("artist_pick_tooltip"))
        self.picker_action.triggered.connect(self.open_picker)
        self.addAction(self.picker_action, QLineEdit.ActionPosition.TrailingPosition)

    # --- autocomplete ---
    def _update_completions(self, text):
        _, segment = _split_current_segment(text[:self.cursorPosition()])
        if len(segment.strip()) < 1:
            self._completer.popup().hide()
            return
        matches = self.catalog.search(segment.strip(), limit=40)
        if not matches or (len(matches) == 1 and matches[0] == segment.strip()):
            self._completer.popup().hide()
            return
        self._model.setStringList(matches)
        self._completer.complete()

    def _insert_completion(self, name):
        head, _ = _split_current_segment(self.text()[:self.cursorPosition()])
        tail = self.text()[self.cursorPosition():]
        self.set_text_as_user(head + name + tail)

    def set_text_as_user(self, text):
        """Set text and notify like a manual edit (so it gets staged)."""
        self.setText(text)
        self.textEdited.emit(text)

    # --- picker ---
    def open_picker(self):
        dlg = ArtistPickerDialog(self.catalog, self.text(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.set_text_as_user(dlg.result_text())


class ArtistField(QWidget):
    """Line edit + hint row. Use `.edit` as the actual field."""
    catalog_changed = pyqtSignal()

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.edit = ArtistLineEdit(catalog, self)
        lay.addWidget(self.edit)

        self.hint_row = QWidget(self)
        h = QHBoxLayout(self.hint_row)
        h.setContentsMargins(0, 0, 0, 0)
        self.lbl_hint = QLabel(self.hint_row)
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color: #F5B027; font-size: 12px;")
        self.btn_apply = QPushButton(self.hint_row)
        self.btn_add = QPushButton(self.hint_row)
        self.btn_add_akv = QPushButton(self.hint_row)
        for b in (self.btn_apply, self.btn_add, self.btn_add_akv):
            b.setStyleSheet("padding: 2px 8px; font-size: 12px;")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(self.lbl_hint, 1)
        h.addWidget(self.btn_apply)
        h.addWidget(self.btn_add)
        h.addWidget(self.btn_add_akv)
        lay.addWidget(self.hint_row)
        self.hint_row.hide()

        self._suggestion = ""
        self._unknown = []
        self.btn_apply.clicked.connect(self._apply_suggestion)
        self.btn_add.clicked.connect(lambda: self._add_unknown(akv=False))
        self.btn_add_akv.clicked.connect(lambda: self._add_unknown(akv=True))
        self.edit.textChanged.connect(self.refresh_hint)
        self.update_texts()

    def update_texts(self):
        self.btn_apply.setText(tr("artist_apply"))
        self.btn_add.setText(tr("artist_add"))
        self.btn_add_akv.setText(tr("artist_add_akv"))
        self.edit.picker_action.setToolTip(tr("artist_pick_tooltip"))
        self.refresh_hint()

    def refresh_hint(self, *_):
        text = self.edit.text().strip()
        self._suggestion, self._unknown = "", []
        if not text:
            self.hint_row.hide()
            return
        suggestion, parts = self.catalog.suggest(text)
        unknown = [p["output"] for p in parts if p["status"] == "unknown"]
        if suggestion and suggestion != text:
            self._suggestion = suggestion
            self.lbl_hint.setText(tr("artist_suggestion").format(suggestion))
            self.btn_apply.show()
            self.btn_add.hide()
            self.btn_add_akv.hide()
            self.hint_row.show()
        elif unknown:
            self._unknown = unknown
            maybe = [c for p in parts if p["status"] == "unknown" for c in p["candidates"][:3]]
            msg = tr("artist_unknown").format(", ".join(unknown))
            if maybe:
                msg += "  " + tr("artist_maybe").format(", ".join(maybe))
            self.lbl_hint.setText(msg)
            self.btn_apply.hide()
            self.btn_add.show()
            self.btn_add_akv.show()
            self.hint_row.show()
        else:
            self.hint_row.hide()

    def _apply_suggestion(self):
        if self._suggestion:
            self.edit.set_text_as_user(self._suggestion)

    def _add_unknown(self, akv=False):
        for name in self._unknown:
            self.catalog.add_user_artist(name, tags=[TAG_AKV] if akv else ())
        self.catalog_changed.emit()
        self.refresh_hint()


class ArtistPickerDialog(QDialog):
    """Search + tick one or more artists. Ticked order = order in the field.
    Right-click an artist to mark it as AKV or remove it from the list."""

    def __init__(self, catalog, current_text, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle(tr("artist_pick_title"))
        self.resize(460, 600)

        lead, feat = split_artists(current_text)
        self.selected = [catalog.canonical(a) for a in lead]
        self.featured = [catalog.canonical(a) for a in feat]

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("artist_search"))
        self.search.textChanged.connect(self._fill)
        self.chk_akv = QCheckBox(tr("artist_only_akv"), self)
        self.chk_akv.toggled.connect(self._fill)
        top.addWidget(self.search, 1)
        top.addWidget(self.chk_akv)
        lay.addLayout(top)

        self.lbl_selected = QLabel(self)
        self.lbl_selected.setWordWrap(True)
        self.lbl_selected.setStyleSheet("color: #96CBD0; font-weight: bold;")
        lay.addWidget(self.lbl_selected)

        self.list = QListWidget(self)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        lay.addWidget(self.list, 1)

        hint = QLabel(tr("artist_picker_hint"), self)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        lay.addWidget(hint)

        self.btn_new = QPushButton(self)
        self.btn_new.clicked.connect(self._add_new)
        lay.addWidget(self.btn_new)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._fill()
        self.search.setFocus()

    def _fill(self, *_):
        text = self.search.text().strip()
        tag = TAG_AKV if self.chk_akv.isChecked() else None
        names = self.catalog.search(text, limit=0, tag=tag)
        # Ticked artists always on top
        sel_keys = {normalize_key(n) for n in self.selected}
        names = [n for n in self.selected if not text or text.lower() in n.lower()] + \
                [n for n in names if normalize_key(n) not in sel_keys]

        self.list.blockSignals(True)
        self.list.clear()
        for name in names:
            label = name
            if self.catalog.is_akv(name):
                label += "   [AKV]"
            years = self.catalog.prins_years(name)
            if years:
                label += "   👑 " + ", ".join(str(y) for y in years)
            years = self.catalog.arendprins_years(name)
            if years:
                label += "   🦅 " + ", ".join(str(y) for y in years)
            aliases = self.catalog.aliases(name)
            if aliases:
                item_tip = tr("artist_aliases").format(", ".join(aliases))
            else:
                item_tip = ""
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(item_tip)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if normalize_key(name) in sel_keys
                               else Qt.CheckState.Unchecked)
            if self.catalog.is_akv(name):
                item.setForeground(QColor("#F5B027"))
            self.list.addItem(item)
        self.list.blockSignals(False)

        exists = bool(text) and self.catalog.contains(text)
        self.btn_new.setVisible(bool(text) and not exists)
        key = "artist_add_new_akv" if self.chk_akv.isChecked() else "artist_add_new"
        self.btn_new.setText(tr(key).format(text))
        self._update_label()

    def _context_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        act_akv = menu.addAction(tr("artist_unmark_akv") if self.catalog.is_akv(name)
                                 else tr("artist_mark_akv"))
        act_remove = menu.addAction(tr("artist_remove"))
        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen == act_akv:
            self.catalog.toggle_tag(name, TAG_AKV)
        elif chosen == act_remove:
            self.catalog.ignore(name)
            self.selected = [n for n in self.selected if normalize_key(n) != normalize_key(name)]
        else:
            return
        self._fill()

    def _on_item_changed(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        key = normalize_key(name)
        if item.checkState() == Qt.CheckState.Checked:
            if key not in {normalize_key(n) for n in self.selected}:
                self.selected.append(name)
        else:
            self.selected = [n for n in self.selected if normalize_key(n) != key]
        self._update_label()

    def _on_double_click(self, item):
        item.setCheckState(Qt.CheckState.Checked)
        self.accept()

    def _add_new(self):
        name = self.search.text().strip()
        if name:
            tags = [TAG_AKV] if self.chk_akv.isChecked() else ()
            self.catalog.add_user_artist(name, tags=tags)
            canon = self.catalog.canonical(name)
            if canon not in self.selected:
                self.selected.append(canon)
            self.search.clear()

    def _update_label(self):
        self.lbl_selected.setText("→ " + (self.result_text() or "—"))

    def result_text(self):
        return self.catalog._join(self.selected, self.featured)


class ArtistDelegate(QStyledItemDelegate):
    """Table delegate: edit an artist cell with autocomplete + picker."""

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog

    def createEditor(self, parent, option, index):
        editor = ArtistLineEdit(self.catalog, parent)
        editor.setMinimumHeight(0)
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.ItemDataRole.EditRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)
