"""Библиотека виджетов приложения."""

from app.gui.widgets.ambiguity_dialog import AmbiguityDialog, CandidateRow
from app.gui.widgets.card import Card, SectionCard, StatCard
from app.gui.widgets.controls import (
    Badge,
    SegmentedFilter,
    Tooltip,
    ghost_button,
    icon_button,
    primary_button,
    secondary_button,
)
from app.gui.widgets.data_table import Column, DataTable, EmptyState
from app.gui.widgets.dialogs import (
    AboutDialog,
    ConfirmDialog,
    MessageDialog,
    ModalDialog,
    ShortcutsDialog,
    ask_confirmation,
    show_message,
)
from app.gui.widgets.drop_zone import FileDropZone
from app.gui.widgets.pdf_viewer import PdfViewer
from app.gui.widgets.progress_panel import ProgressPanel
from app.gui.widgets.search_entry import SearchEntry
from app.gui.widgets.sidebar import NavItem, Sidebar
from app.gui.widgets.toast import Toast, ToastManager

__all__ = [
    "AboutDialog",
    "AmbiguityDialog",
    "Badge",
    "CandidateRow",
    "Card",
    "Column",
    "ConfirmDialog",
    "DataTable",
    "EmptyState",
    "FileDropZone",
    "MessageDialog",
    "ModalDialog",
    "NavItem",
    "PdfViewer",
    "ProgressPanel",
    "SearchEntry",
    "SectionCard",
    "SegmentedFilter",
    "ShortcutsDialog",
    "Sidebar",
    "StatCard",
    "Toast",
    "ToastManager",
    "Tooltip",
    "ask_confirmation",
    "ghost_button",
    "icon_button",
    "primary_button",
    "secondary_button",
    "show_message",
]
