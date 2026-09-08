"""Делегированный доступ к контуру Dedicated-клиента (Доп. №1 разд. 49.1, 49.3).

У режима Dedicated данные клиента лежат в ДРУГОМ арендаторе. До этого среза
сводка внимания по портфелю честно писала «не сведено»: читать чужой контур
было нечем, и тихий ноль был бы хуже — он выглядел бы как «у клиента всё в
порядке».

Здесь — чистые правила: КОГДА аутсорсеру можно читать контур клиента. Ни SQL,
ни сессий: решение отделено от исполнения, потому что цена ошибки тут не
«медленно», а «чужие персональные данные».

## Три условия, и все обязательны

**1. Клиент действительно ведётся отдельным контуром.** Режим Dedicated и
указанный арендатор — иначе делегировать нечего.

**2. Контур клиента — ПОТОМОК арендатора-аутсорсера.** Это основание, а не
формальность: без него достаточно было бы вписать в карточку любой чужой
слаг, и платформа сама пошла бы читать чужие данные. Иерархия арендаторов
(BIZ-52) — единственное место, где записано «этот контур заведён под этим
аутсорсером».

**3. Есть действующее согласие клиента.** Тот же документ-основание, что и у
работы «от имени» (разд. 66): истёкшее или отозванное согласие равно его
отсутствию. Согласие лежит у аутсорсера, потому что это ЕГО обязательство —
доказать основание обработки.

## Отказ обязан называть причину

«Не сведено» без объяснения читается как поломка платформы, а не как «клиент
не дал согласия». Поэтому вердикт несёт причину словами — её видно на экране
портфеля, и специалист понимает, что делать: получить согласие, поднять
контур, связать иерархию.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domains.managed_clients.consent import ClientConsent, active_consent
from app.domains.managed_clients.lifecycle import ManagedClientMode

__all__ = [
    "DelegationVerdict",
    "NO_CONSENT_REASON",
    "NO_OWN_TENANT_REASON",
    "NOT_A_CHILD_REASON",
    "TENANT_INACTIVE_REASON",
    "TENANT_MISSING_REASON",
    "evaluate_delegated_read",
]

NO_OWN_TENANT_REASON = (
    "Клиент помечен как ведомый отдельным контуром, но сам контур не указан — " "читать нечего"
)

NOT_A_CHILD_REASON = (
    "Контур клиента не заведён под этим аутсорсером: без иерархии арендаторов "
    "у делегирования нет основания"
)

TENANT_MISSING_REASON = "Контур с указанным именем не заведён на платформе — читать нечего"

TENANT_INACTIVE_REASON = "Контур клиента отключён — сводка по нему не считается"

NO_CONSENT_REASON = (
    "Нет действующего согласия клиента на делегированный доступ — сводка по "
    "его контуру не собирается"
)


@dataclass(frozen=True)
class DelegationVerdict:
    """Можно ли читать контур клиента и, если нет, почему."""

    allowed: bool
    tenant_slug: str | None = None
    reason: str | None = None

    @classmethod
    def allow(cls, tenant_slug: str) -> DelegationVerdict:
        return cls(allowed=True, tenant_slug=tenant_slug)

    @classmethod
    def deny(cls, reason: str) -> DelegationVerdict:
        return cls(allowed=False, reason=reason)


def evaluate_delegated_read(
    *,
    mode: ManagedClientMode,
    client_tenant_slug: str | None,
    client_tenant_exists: bool,
    client_tenant_parent_id: str | None,
    client_tenant_is_active: bool,
    outsourcer_tenant_id: str,
    consents: list[ClientConsent] | tuple[ClientConsent, ...],
    now: datetime,
) -> DelegationVerdict:
    """Вердикт по трём условиям. Порядок проверок = порядок причин на экране.

    ``client_tenant_parent_id`` — ``None``, если контура нет вовсе или у него
    нет родителя; и то и другое означает «основания нет».
    """

    if mode is not ManagedClientMode.DEDICATED:
        # Не Dedicated — делегировать нечего: данные и так в контуре аутсорсера.
        return DelegationVerdict.deny(NO_OWN_TENANT_REASON)
    if not (client_tenant_slug or "").strip():
        return DelegationVerdict.deny(NO_OWN_TENANT_REASON)
    if not client_tenant_exists:
        # Имя вписано, а контура нет: «отключён» тут соврало бы — человек пошёл
        # бы включать то, чего не существует.
        return DelegationVerdict.deny(TENANT_MISSING_REASON)
    if not client_tenant_parent_id or str(client_tenant_parent_id) != str(outsourcer_tenant_id):
        return DelegationVerdict.deny(NOT_A_CHILD_REASON)
    if not client_tenant_is_active:
        return DelegationVerdict.deny(TENANT_INACTIVE_REASON)
    if active_consent(consents, now=now) is None:
        return DelegationVerdict.deny(NO_CONSENT_REASON)
    return DelegationVerdict.allow(str(client_tenant_slug).strip())
