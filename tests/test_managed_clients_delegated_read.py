"""Делегированное чтение контура Dedicated-клиента (BIZ-49, разд. 49.1 и 49.3).

ЗАЧЕМ. У режима Dedicated данные клиента лежат в ДРУГОМ арендаторе, и сводка
внимания по портфелю честно писала «не сведено»: читать чужой контур было
нечем. Теперь читает — но только при основании (иерархия арендаторов) и
действующем согласии клиента.

ЧТО ПРОВЕРЯЕТСЯ: три условия по отдельности; отказ называет ПРИЧИНУ, а не
молчит нулём; чужой контур без иерархии не читается, даже если слаг вписан в
карточку руками.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.managed_clients.consent import ClientConsent
from app.domains.managed_clients.delegation import (
    NO_CONSENT_REASON,
    NO_OWN_TENANT_REASON,
    NOT_A_CHILD_REASON,
    TENANT_INACTIVE_REASON,
    TENANT_MISSING_REASON,
    evaluate_delegated_read,
)
from app.domains.managed_clients.lifecycle import ManagedClientMode


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _consent(*, revoked: bool = False, expired: bool = False) -> ClientConsent:
    now = _now()
    return ClientConsent(
        client_id="c-1",
        document_ref="Поручение №1",
        granted_at=now - timedelta(days=1),
        expires_at=now - timedelta(hours=1) if expired else now + timedelta(days=30),
        revoked_at=now if revoked else None,
    )


def _verdict(**over):
    kwargs = dict(
        mode=ManagedClientMode.DEDICATED,
        client_tenant_slug="client-tenant",
        client_tenant_exists=True,
        client_tenant_parent_id="outsourcer-1",
        client_tenant_is_active=True,
        outsourcer_tenant_id="outsourcer-1",
        consents=[_consent()],
        now=_now(),
    )
    kwargs.update(over)
    return evaluate_delegated_read(**kwargs)


class TestОснованиеДляЧтения:
    def test_все_условия_соблюдены_читать_можно(self) -> None:
        verdict = _verdict()

        assert verdict.allowed
        assert verdict.tenant_slug == "client-tenant"

    def test_чужой_контур_без_иерархии_не_читается(self) -> None:
        """Главная защита: вписать чужой слаг в карточку руками недостаточно.

        Иерархия арендаторов — единственное место, где записано «этот контур
        заведён под этим аутсорсером».
        """

        verdict = _verdict(client_tenant_parent_id="кто-то-другой")

        assert not verdict.allowed
        assert verdict.reason == NOT_A_CHILD_REASON

    def test_контур_без_родителя_не_читается(self) -> None:
        verdict = _verdict(client_tenant_parent_id=None)

        assert not verdict.allowed
        assert verdict.reason == NOT_A_CHILD_REASON

    def test_без_согласия_не_читается(self) -> None:
        verdict = _verdict(consents=[])

        assert not verdict.allowed
        assert verdict.reason == NO_CONSENT_REASON

    def test_отозванное_согласие_равно_отсутствию(self) -> None:
        verdict = _verdict(consents=[_consent(revoked=True)])

        assert not verdict.allowed
        assert verdict.reason == NO_CONSENT_REASON

    def test_истёкшее_согласие_равно_отсутствию(self) -> None:
        verdict = _verdict(consents=[_consent(expired=True)])

        assert not verdict.allowed
        assert verdict.reason == NO_CONSENT_REASON

    def test_контура_с_таким_именем_нет(self) -> None:
        """«Отключён» тут соврало бы: человек пошёл бы включать несуществующее."""

        verdict = _verdict(client_tenant_exists=False)

        assert not verdict.allowed
        assert verdict.reason == TENANT_MISSING_REASON

    def test_отключённый_контур_не_читается(self) -> None:
        verdict = _verdict(client_tenant_is_active=False)

        assert not verdict.allowed
        assert verdict.reason == TENANT_INACTIVE_REASON

    def test_без_указанного_контура_читать_нечего(self) -> None:
        verdict = _verdict(client_tenant_slug=None)

        assert not verdict.allowed
        assert verdict.reason == NO_OWN_TENANT_REASON

    def test_lightweight_клиенту_делегирование_не_нужно(self) -> None:
        """Его данные и так в контуре аутсорсера — делегировать нечего."""

        verdict = _verdict(mode=ManagedClientMode.LIGHTWEIGHT)

        assert not verdict.allowed

    def test_отказ_всегда_называет_причину(self) -> None:
        """«Не сведено» без объяснения читается как поломка платформы."""

        for over in (
            {"consents": []},
            {"client_tenant_parent_id": None},
            {"client_tenant_exists": False},
            {"client_tenant_is_active": False},
            {"client_tenant_slug": None},
        ):
            verdict = _verdict(**over)
            assert not verdict.allowed
            assert verdict.reason and len(verdict.reason) > 20, over


@pytest.mark.asyncio
async def test_сорвавшееся_чтение_даёт_не_сведено_а_не_ноль(monkeypatch) -> None:
    """Ноль читался бы как «у клиента всё в порядке» — худшая ошибка сводки.

    Контур мог быть переименован или недоступен. Проверяем ИМЕННО это: чтение
    сорвалось — ответ «не сведено», а не спокойная зелёная строка.
    """

    from app.services import delegated_attention

    def _boom(*args, **kwargs):
        raise RuntimeError("контур недоступен")

    monkeypatch.setattr(delegated_attention, "AsyncSessionLocal", _boom)

    counts = await delegated_attention.collect_dedicated_client_signals(
        tenant_slug="client-tenant",
        tenant_id="00000000-0000-0000-0000-000000000000",
        today=_now().date(),
        now=_now(),
    )

    assert counts is None
