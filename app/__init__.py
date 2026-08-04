"""BALTON CertMatcher — автоматический подбор сертификатов соответствия.

Пакет верхнего уровня. Содержит только метаданные приложения, чтобы импорт
``app`` оставался максимально дешёвым (важно для времени старта EXE).
"""

from __future__ import annotations

from app.core.constants import APP_NAME, APP_VERSION

__all__ = ["APP_NAME", "APP_VERSION"]
