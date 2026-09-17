"""BIZ-52 срез-5: чей юридический текст показывать (разд. 52.2, четвёртый пункт).

Правила чистые — проверяются примерами без базы.
"""

from __future__ import annotations

from app.domains.reseller.legal import (
    LEGAL_KIND_TITLES,
    LegalDocument,
    LegalDocumentKind,
    resolve_legal_document,
)

OFFER = LegalDocumentKind.OFFER


def _doc(source: str, body: str = "Текст оферты", version: int = 1) -> LegalDocument:
    return LegalDocument(
        kind=OFFER, title="Публичная оферта", body=body, version=version, source=source
    )


class TestЧейТекстПоказать:
    def test_без_текстов_показывать_нечего(self) -> None:
        assert resolve_legal_document(OFFER, own=None, reseller=None) is None

    def test_клиент_партнёра_видит_оферту_партнёра(self) -> None:
        result = resolve_legal_document(OFFER, own=None, reseller=_doc("reseller"))
        assert result is not None
        assert result.source == "reseller"

    def test_свой_текст_побеждает_текст_партнёра(self) -> None:
        result = resolve_legal_document(OFFER, own=_doc("self"), reseller=_doc("reseller"))
        assert result is not None
        assert result.source == "self"

    def test_пустой_текст_ступень_не_занимает(self) -> None:
        """Заведённая, но пустая редакция не должна перекрывать текст партнёра.

        Иначе черновик у клиента оставил бы его вообще без оферты — хуже, чем
        если бы он ничего не заводил.
        """

        result = resolve_legal_document(
            OFFER, own=_doc("self", body="   "), reseller=_doc("reseller")
        )
        assert result is not None
        assert result.source == "reseller"


class TestДокументНеСмешивается:
    def test_возвращается_целая_редакция_а_не_склейка(self) -> None:
        """Половина оферты партнёра и половина платформенной — это подделка."""

        own = LegalDocument(kind=OFFER, title="Своя", body="Своё тело", version=7, source="self")
        reseller = LegalDocument(
            kind=OFFER, title="Партнёрская", body="Чужое тело", version=2, source="reseller"
        )

        result = resolve_legal_document(OFFER, own=own, reseller=reseller)

        assert result == own
        assert result.title == "Своя"
        assert result.version == 7


class TestВидыТекстов:
    def test_все_три_вида_из_тз_объявлены(self) -> None:
        assert {kind.value for kind in LegalDocumentKind} == {
            "offer",
            "privacy",
            "consent",
        }

    def test_у_каждого_вида_есть_человеческое_название(self) -> None:
        for kind in LegalDocumentKind:
            assert LEGAL_KIND_TITLES[kind]
