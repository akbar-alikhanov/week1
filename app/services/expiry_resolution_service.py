"""Подбор наиболее подходящего срока годности ДО поиска сертификата.

Новый, полностью самостоятельный этап конвейера обработки заказа: он
выполняется ПЕРЕД существующим алгоритмом подбора сертификата
(:class:`~app.services.matching_service.MatchingService`) и не изменяет, не
переписывает и не заменяет его — только определяет для каждой строки заказа
наиболее подходящий срок годности (если он ещё не указан в самом заказе) и
передаёт готовую строку дальше, в уже существующий, нетронутый подбор.

Источник данных — отдельная от базы сертификатов Excel-таблица «сроков
годности и остатков»: она отвечает на вопрос «какие партии этого товара
сейчас есть на складе и когда у них истекает срок», а не «какой сертификат
подтверждает товар». Одна и та же строка заказа может встречаться в этой
базе много раз — по одной записи на партию/срок.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.core.events import ProgressReporter
from app.core.text import normalize
from app.models.matching import MatchStatus
from app.models.order import OrderRow
from app.repositories.expiry_stock_repository import ExpiryStockRepository
from app.services.matching_service import MatchingService

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExpiryExclusion:
    """Причина, по которой строка заказа не передаётся в обычный подбор сертификата.

    Attributes:
        note: Пояснение для пользователя (итоговый Excel, отчёт, история).
        not_in_database: Признак того, что товар отсутствует в базе сроков
            годности вообще — единственный случай с отдельным визуальным
            выделением (жёлтая заливка и зачёркнутый текст, п. «Если товар
            не найден» требования). Второй возможный случай — товар в базе
            есть, но подходящий срок подобрать не удалось (недостаточно
            количества на любой отдельной партии, либо ни для одного срока
            с достаточным количеством не нашёлся сертификат) — получает
            обычное выделение «не найдено», как и любая другая ненайденная
            строка, без специального форматирования.
    """

    note: str
    not_in_database: bool = False


class ExpiryResolutionService:
    """Подбирает срок годности для строк заказа перед поиском сертификата.

    Если база сроков годности не настроена (ни разу не импортирована —
    пустая таблица), сервис не делает вообще ничего: ни одна строка не
    исключается и не изменяется. Это осознанное решение: новая функция
    должна быть полностью незаметна для тех, кто её не настроил, и не
    менять поведение приложения по умолчанию.
    """

    def __init__(
        self, expiry_repository: ExpiryStockRepository, matching_service: MatchingService
    ) -> None:
        """Создаёт сервис подбора срока годности.

        Args:
            expiry_repository: База сроков годности и остатков (индекс над Excel).
            matching_service: Существующий, неизменяемый сервис подбора
                сертификата — используется только для пробных вызовов
                ``match_row`` при проверке «найдётся ли сертификат на этот
                срок», без единой правки в самом сервисе.
        """
        self._stock = expiry_repository
        self._matching = matching_service

    def resolve_rows(
        self, rows: Sequence[OrderRow], *, reporter: ProgressReporter | None = None
    ) -> dict[int, ExpiryExclusion]:
        """Подбирает срок годности для каждой строки заказа.

        Строкам, для которых подходящий срок найден (или у которых он уже
        был указан в заказе), метод ничего дополнительно не сообщает —
        ``row.requested_expiry`` уже мутирован на месте, и дальше строка
        идёт в обычный, неизменённый подбор сертификата.

        Args:
            rows: Строки заказа.
            reporter: Приёмник прогресса (пробные подборы на больших
                заказах небыстры).

        Returns:
            Отображение «номер строки → причина исключения» для строк,
            которые не должны передаваться в обычный подбор сертификата.
            Пустой словарь, если база сроков годности не настроена или все
            строки успешно прошли этап (или уже имели указанный срок).
        """
        if self._stock.count() == 0:
            return {}

        if reporter is not None:
            reporter.start(len(rows), "Подбор срока годности…", "expiry")

        excluded: dict[int, ExpiryExclusion] = {}
        for index, row in enumerate(rows, start=1):
            exclusion = self._resolve_row(row)
            if exclusion is not None:
                excluded[row.row_number] = exclusion
            if reporter is not None:
                reporter.advance(1, f"Обработано {index} из {len(rows)}", "expiry")

        if reporter is not None:
            reporter.finish("Подбор срока годности завершён", "expiry")
        return excluded

    # ------------------------------------------------------------- строка
    def _resolve_row(self, row: OrderRow) -> ExpiryExclusion | None:
        """Определяет срок годности для одной строки заказа.

        Реализует алгоритм требования пошагово:

        1. Найти все партии товара в базе сроков (точное совпадение полного
           системного названия).
        2. Отсортировать от самого нового срока к самому старому.
        3. Для каждого срока — хватает ли количества партии для заказа;
           если нет, перейти к следующему (более старому) сроку.
        4. Если количества достаточно, пробным вызовом существующего
           ``MatchingService.match_row`` проверить, находится ли сертификат
           на этот срок. Найден — использовать этот срок и остановиться.
           Не найден — вернуть срок в исходное состояние и перейти к
           следующему более старому сроку.

        Args:
            row: Строка заказа (мутируется при успехе).

        Returns:
            Причина исключения строки из обычного подбора либо ``None``,
            если строку можно передавать в обычный подбор как обычно —
            либо потому что срок уже был в заказе, либо потому что новый
            этап успешно его подобрал.
        """
        if row.requested_expiry is not None:
            # Заказ уже указывает требуемый срок — это осознанный выбор
            # человека, новый этап его не переопределяет и не проверяет.
            return None

        entries = self._stock.find_by_product_name(normalize(row.product_name))
        if not entries:
            return ExpiryExclusion(note="Товар отсутствует в базе сроков.", not_in_database=True)

        newest_first = sorted(
            entries, key=lambda entry: entry.expiry_date or date.min, reverse=True
        )

        required_quantity = row.quantity or 0.0
        any_sufficient_quantity = False
        for entry in newest_first:
            if entry.quantity < required_quantity:
                continue
            any_sufficient_quantity = True

            row.requested_expiry = entry.expiry_date
            trial = self._matching.match_row(row)
            if trial.status is MatchStatus.MATCHED:
                _LOGGER.debug(
                    "Срок годности подобран для «%s»: %s", row.product_name, entry.expiry_date
                )
                return None
            row.requested_expiry = None

        if not any_sufficient_quantity:
            # «Ничего пока не делать» для случая суммарно достаточного, но
            # раздельно недостаточного остатка — п. «Если количества не
            # хватает» требования: логика частичного резервирования по
            # нескольким срокам сразу будет реализована позже.
            return ExpiryExclusion(
                note="Недостаточное количество ни на одном сроке базы — требуется ручная обработка."
            )

        return ExpiryExclusion(
            note="Ни для одного срока с достаточным количеством не найден сертификат."
        )
