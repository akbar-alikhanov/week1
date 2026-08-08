"""Взвешенная оценка кандидатов.

Итоговое решение принимается по трём составляющим с настраиваемыми весами:

* совпадение наименования — 50 %;
* совпадение объёма — 30 %;
* соответствие срока — 20 %.

Веса заданы в настройках и нормируются к сумме 1.0, поэтому пользователь
может менять их произвольно, не рискуя получить оценку больше единицы.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.config.settings import MatchingSettings
from app.core.dates import expiry_similarity
from app.core.units import Volume, extract_volumes, volume_similarity
from app.models.certificate_product import CertificateProduct
from app.models.matching import ScoreBreakdown
from app.models.order import OrderRow

#: Понижающий коэффициент для случая, когда совпадение обеспечено только
#: семантической моделью. Отражает её меньшую надёжность по сравнению с
#: прямым текстовым совпадением, но оставляет достаточно, чтобы кандидат
#: прошёл порог минимальной оценки наименования.
_SEMANTIC_SOLO_FACTOR = 0.9


@dataclass(frozen=True, slots=True)
class ScoringContext:
    """Контекст, общий для всех оценок в рамках одной обработки заказа.

    Вынесение контекста наружу избавляет от пересоздания настроек и вычисления
    текущей даты на каждой из десятков тысяч пар «строка × кандидат».

    Attributes:
        settings: Параметры алгоритма подбора.
        reference_date: Дата, относительно которой проверяется срок действия.
    """

    settings: MatchingSettings
    reference_date: date

    @classmethod
    def create(cls, settings: MatchingSettings, *, today: date | None = None) -> ScoringContext:
        """Создаёт контекст оценки.

        Args:
            settings: Параметры алгоритма.
            today: Опорная дата (по умолчанию — сегодня).

        Returns:
            Готовый контекст.
        """
        return cls(settings=settings, reference_date=today or date.today())


def combine_name_score(lexical: float, semantic: float | None, settings: MatchingSettings) -> float:
    """Объединяет лексическую и семантическую оценки наименования.

    Семантика не заменяет лексику, а дополняет её. Учитываются три сценария:

    * уверенное текстовое совпадение — модель не должна его ухудшить;
    * частичное совпадение обоих каналов — взвешенная комбинация;
    * совпадение только по смыслу («TP Herbal» = «Лечебные травы») — лексика
      здесь равна нулю, и семантика выступает самостоятельным свидетельством
      с небольшой понижающей поправкой на неточность модели.

    Args:
        lexical: Оценка нечёткого сравнения ``[0..1]``.
        semantic: Оценка семантической близости ``[0..1]`` либо ``None``.
        settings: Параметры алгоритма.

    Returns:
        Итоговая оценка наименования ``[0..1]``.
    """
    if semantic is None:
        return lexical
    semantic_weight = settings.semantic_weight
    blended = lexical * (1.0 - semantic_weight) + semantic * semantic_weight
    solo = semantic * _SEMANTIC_SOLO_FACTOR
    return round(max(lexical, blended, solo), 6)


def score_candidate(
    row: OrderRow,
    certificate: CertificateProduct,
    *,
    lexical: float,
    semantic: float | None,
    context: ScoringContext,
) -> ScoreBreakdown:
    """Вычисляет итоговую оценку пары «строка заказа — сертификат».

    Args:
        row: Строка заказа.
        certificate: Сертификат-кандидат.
        lexical: Оценка лексического сравнения.
        semantic: Оценка семантического сравнения (``None``, если не считалась).
        context: Общий контекст оценки.

    Returns:
        Детализированная оценка.
    """
    settings = context.settings
    weight_name, weight_volume, weight_expiry = settings.normalized_weights()

    name_score = combine_name_score(lexical, semantic, settings)

    volume_score = volume_similarity(
        row.volume,
        certificate.volume,
        tolerance_ratio=settings.volume_tolerance_ratio,
        missing_score=settings.missing_volume_score,
    )

    expiry_score = expiry_similarity(
        certificate.expiry_date,
        row.requested_expiry,
        reference=context.reference_date,
        tolerance_days=settings.expiry_tolerance_days,
        missing_score=settings.missing_expiry_score,
        expired_score=0.0 if settings.require_valid_expiry else 0.25,
    )

    total = name_score * weight_name + volume_score * weight_volume + expiry_score * weight_expiry

    return ScoreBreakdown(
        name=round(name_score, 6),
        volume=round(volume_score, 6),
        expiry=round(expiry_score, 6),
        total=round(total, 6),
        lexical=round(lexical, 6),
        semantic=None if semantic is None else round(semantic, 6),
        weights=(round(weight_name, 4), round(weight_volume, 4), round(weight_expiry, 4)),
    )


def is_hard_mismatch(
    row: OrderRow,
    certificate: CertificateProduct,
    context: ScoringContext,
    *,
    ignore_expiry_tolerance: bool = False,
) -> bool:
    """Проверяет наличие безусловного несоответствия.

    Некоторые расхождения не компенсируются никакими весами: сертификат с
    истёкшим сроком нельзя приложить к поставке, объём 100 мл нельзя
    подтвердить сертификатом на 500 мл, а если в заказе указан требуемый
    срок годности — сертификат, чей срок отличается от него больше чем на
    ``expiry_tolerance_days`` (в любую сторону, с учётом года), не может
    быть кандидатом вообще, каким бы похожим ни было название.

    Args:
        row: Строка заказа.
        certificate: Сертификат-кандидат.
        context: Общий контекст оценки.
        ignore_expiry_tolerance: Не отбраковывать по расхождению срока.
            Используется ИСКЛЮЧИТЕЛЬНО ручным (вторым) этапом подбора срока
            годности
            (:meth:`~app.services.matching_service.MatchingService.find_expiry_alternatives`)
            для поиска ближайших вариантов ПОСЛЕ того, как обычный строгий
            подбор уже не нашёл ничего в пределах допуска — результат такого
            поиска никогда не выбирается автоматически, только предлагается
            пользователю. Остальные проверки (просрочка, объём) действуют
            как обычно.

    Returns:
        ``True``, если кандидат должен быть отброшен независимо от оценки.
    """
    settings = context.settings

    if (
        settings.require_valid_expiry
        and certificate.expiry_date is not None
        and certificate.expiry_date < context.reference_date
    ):
        return True

    if (
        not ignore_expiry_tolerance
        and row.requested_expiry is not None
        and certificate.expiry_date is not None
        and abs((certificate.expiry_date - row.requested_expiry).days)
        > settings.expiry_tolerance_days
    ):
        return True

    row_volume = row.volume
    certificate_volume = certificate.volume
    if row_volume is None or certificate_volume is None:
        return False

    if row_volume.dimension != certificate_volume.dimension:
        return True

    similarity = volume_similarity(
        row_volume,
        certificate_volume,
        tolerance_ratio=settings.volume_tolerance_ratio,
        missing_score=settings.missing_volume_score,
    )
    if similarity <= 0.0:
        return True

    if settings.strict_volume_match and similarity < 1.0:
        # Строгий режим: сертификат выдаётся на конкретную фасовку, поэтому
        # 150 мл не подтверждает 100 мл. Исключение — сертификаты, покрывающие
        # сразу несколько фасовок («Сироп 100, 150, 200 мл»): для них проверяем
        # все объёмы, упомянутые в наименовании.
        return not _covers_volume(certificate, row_volume, settings.volume_tolerance_ratio)

    return False


def _covers_volume(certificate: CertificateProduct, target: Volume, tolerance: float) -> bool:
    """Проверяет, покрывает ли сертификат требуемый объём.

    Args:
        certificate: Сертификат-кандидат.
        target: Объём из строки заказа.
        tolerance: Относительный допуск сравнения.

    Returns:
        ``True``, если среди объёмов, упомянутых в сертификате, есть нужный.
    """
    for volume in extract_volumes(certificate.product_name):
        if volume.dimension != target.dimension:
            continue
        if volume_similarity(volume, target, tolerance_ratio=tolerance) >= 1.0:
            return True
    return False
