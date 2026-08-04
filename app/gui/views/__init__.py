"""Разделы приложения."""

from app.gui.views.aliases_view import AliasesView
from app.gui.views.base_view import BaseView
from app.gui.views.certificates_view import CertificatesView
from app.gui.views.dashboard_view import DashboardView
from app.gui.views.history_view import HistoryView
from app.gui.views.logs_view import LogsView
from app.gui.views.settings_view import SettingsView

__all__ = [
    "AliasesView",
    "BaseView",
    "CertificatesView",
    "DashboardView",
    "HistoryView",
    "LogsView",
    "SettingsView",
]
