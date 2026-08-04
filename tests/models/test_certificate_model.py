"""Тесты доменной модели сертификата."""

from __future__ import annotations

import datetime as dt

from app.models.certificate import Certificate


class TestPostInit:
    """Проверки автоматического вычисления производных полей."""

    def test_normalized_name_computed(self) -> None:
        """Нормализованное имя вычисляется автоматически из product_name."""
        certificate = Certificate(product_name="Лечебные Травы 100 МЛ", pdf_path="/c/1.pdf")
        assert certificate.normalized_name == "лечебные травы 100 ml"

    def test_pdf_name_derived_from_path(self) -> None:
        """Имя файла берётся из пути, если не задано явно."""
        certificate = Certificate(product_name="Товар", pdf_path="/some/dir/183255.pdf")
        assert certificate.pdf_name == "183255.pdf"

    def test_explicit_pdf_name_not_overridden(self) -> None:
        """Явно заданное имя файла не перезаписывается."""
        certificate = Certificate(
            product_name="Товар", pdf_path="/some/dir/183255.pdf", pdf_name="custom.pdf"
        )
        assert certificate.pdf_name == "custom.pdf"


class TestProperties:
    """Проверки вычисляемых свойств."""

    def test_is_expired_true_for_past_date(self) -> None:
        """Дата в прошлом считается истёкшей."""
        certificate = Certificate(
            product_name="Товар", pdf_path="/c/1.pdf", expiry_date=dt.date(2000, 1, 1)
        )
        assert certificate.is_expired

    def test_is_expired_false_for_future_date(self) -> None:
        """Дата в будущем не считается истёкшей."""
        certificate = Certificate(
            product_name="Товар", pdf_path="/c/1.pdf", expiry_date=dt.date(2099, 1, 1)
        )
        assert not certificate.is_expired

    def test_is_expired_false_without_date(self) -> None:
        """Отсутствие срока не считается истечением."""
        certificate = Certificate(product_name="Товар", pdf_path="/c/1.pdf")
        assert not certificate.is_expired

    def test_display_number_uses_certificate_number(self) -> None:
        """При наличии номера сертификата он используется как display_number."""
        certificate = Certificate(
            product_name="Товар", pdf_path="/c/1.pdf", certificate_number="UZ.183255"
        )
        assert certificate.display_number == "UZ.183255"

    def test_display_number_falls_back_to_filename(self) -> None:
        """Без номера используется имя файла без расширения."""
        certificate = Certificate(product_name="Товар", pdf_path="/c/183600.pdf")
        assert certificate.display_number == "183600"

    def test_volume_property_reconstructs_volume_object(self) -> None:
        """Свойство volume собирает объект Volume из сохранённых полей."""
        certificate = Certificate(
            product_name="Товар", pdf_path="/c/1.pdf", volume_value=100.0, volume_unit="ml"
        )
        volume = certificate.volume
        assert volume is not None
        assert volume.base_value == 100.0
        assert volume.base_unit == "ml"

    def test_volume_property_none_without_value(self) -> None:
        """Без значения объёма свойство возвращает None."""
        certificate = Certificate(product_name="Товар", pdf_path="/c/1.pdf")
        assert certificate.volume is None


class TestRowRoundtrip:
    """Проверки сериализации в строку БД и обратно."""

    def test_to_row_and_from_row_preserve_data(self) -> None:
        """Полный цикл to_row → from_row сохраняет все значимые поля."""
        original = Certificate(
            product_name="Лечебные травы 100 мл",
            pdf_path="/c/1.pdf",
            brand="Herbal Doctor",
            certificate_number="UZ.183255",
            expiry_date=dt.date(2029, 3, 22),
            volume_value=100.0,
            volume_unit="ml",
        )
        row = original.to_row()
        restored = Certificate.from_row(row)

        assert restored.product_name == original.product_name
        assert restored.brand == original.brand
        assert restored.certificate_number == original.certificate_number
        assert restored.expiry_date == original.expiry_date
        assert restored.volume_value == original.volume_value
