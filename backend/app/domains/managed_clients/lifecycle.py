"""BIZ-49 срез-1 (разд. 49.1): правила ведения клиента аутсорсером.

Чистые функции без БД — как ``domains/committees/lifecycle.py``. Здесь живёт
то, что нельзя отдать на откуп интерфейсу:

* **инварианты режима ведения.** Lightweight — клиент как организация внутри
  пространства аутсорсера; Dedicated — собственный изолированный tenant
  клиента. Позволить строке быть «и там, и там» значит завести два расходящихся
  набора данных и потерять их при переводе (разд. 49.1 требует перевод БЕЗ
  потери истории);
* **переходы статуса договора** — расторгнутый договор не воскресает правкой
  поля: это меняет биллинг и доступы;
* **сигналы портфеля** — «истекает» это свойство ДОГОВОРА, а не даты: у
  расторгнутого срок неинтересен, и шум в портфеле топит настоящие сигналы.
"""

from __future__ import annotations

import enum
import re
from datetime import date

__all__ = [
    "ContractStatus",
    "ManagedClientMode",
    "ManagedClientTransitionError",
    "contract_days_left",
    "is_contract_expiring",
    "validate_contract_transition",
    "validate_conversion_to_dedicated",
    "validate_mode_binding",
]


class ManagedClientMode(str, enum.Enum):
    LIGHTWEIGHT = "lightweight"
    DEDICATED = "dedicated"


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class ManagedClientTransitionError(ValueError):
    """Нарушен инвариант режима или недопустимый переход статуса договора."""


_ALLOWED_CONTRACT: dict[ContractStatus, set[ContractStatus]] = {
    ContractStatus.DRAFT: {ContractStatus.ACTIVE, ContractStatus.TERMINATED},
    ContractStatus.ACTIVE: {ContractStatus.SUSPENDED, ContractStatus.TERMINATED},
    ContractStatus.SUSPENDED: {ContractStatus.ACTIVE, ContractStatus.TERMINATED},
    # Расторжение — терминальное состояние: «оживление» это новый договор.
    ContractStatus.TERMINATED: set(),
}


def validate_mode_binding(
    mode: ManagedClientMode, *, company_id: str | None, tenant_slug: str | None
) -> None:
    """Проверить, что режим ведения связан ровно с тем, чем должен."""

    if mode is ManagedClientMode.LIGHTWEIGHT:
        if not company_id:
            raise ManagedClientTransitionError(
                "Lightweight-клиент обязан ссылаться на организацию в пространстве аутсорсера"
            )
        if tenant_slug:
            raise ManagedClientTransitionError(
                "Lightweight-клиент не может владеть собственным арендатором"
            )
        return
    if not tenant_slug:
        raise ManagedClientTransitionError(
            "Dedicated-клиент обязан ссылаться на собственного арендатора"
        )
    # company_id у dedicated законен: после перевода из lightweight он остаётся
    # ссылкой на историю в пространстве аутсорсера.


def validate_contract_transition(current: ContractStatus, target: ContractStatus) -> None:
    if target not in _ALLOWED_CONTRACT.get(current, set()):
        raise ManagedClientTransitionError(
            f"Недопустимый переход договора {current.value} -> {target.value}"
        )


def contract_days_left(ends_at: date | None, *, today: date) -> int | None:
    """Дней до конца договора; отрицательное значение = договор уже просрочен."""

    if ends_at is None:
        return None
    return (ends_at - today).days


def is_contract_expiring(
    status: ContractStatus,
    ends_at: date | None,
    *,
    today: date,
    horizon_days: int,
) -> bool:
    """Сигнал портфеля «договор истекает/истёк» — только для живого договора."""

    if status not in (ContractStatus.ACTIVE, ContractStatus.SUSPENDED):
        return False
    days = contract_days_left(ends_at, today=today)
    if days is None:
        return False
    return days <= horizon_days


#: Слаг попадает в имя схемы БД (``tenant_{slug}``) и в заголовок ``X-Tenant`` —
#: формат обязан быть безопасным для обоих применений.
_TENANT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def validate_conversion_to_dedicated(
    *,
    mode: ManagedClientMode,
    contract_status: ContractStatus,
    target_slug: str,
) -> None:
    """Правила перевода Lightweight → Dedicated (разд. 49.1).

    * переводится только Lightweight: у Dedicated арендатор уже есть, и второй
      перевод означал бы ДВА арендатора с непонятно чьей историей;
    * расторгнутого клиента не переводят: перевод — часть живого ведения,
      а не операция над архивом;
    * слаг проверяется до создания арендатора: битое имя схемы БД всплыло бы
      только при первом обращении к данным клиента.
    """

    if mode is ManagedClientMode.DEDICATED:
        raise ManagedClientTransitionError(
            "Клиент уже ведётся в собственном арендаторе — повторный перевод невозможен"
        )
    if contract_status is ContractStatus.TERMINATED:
        raise ManagedClientTransitionError(
            "Клиент с расторгнутым договором не переводится: перевод — часть живого ведения"
        )
    if not _TENANT_SLUG_RE.fullmatch(target_slug):
        raise ManagedClientTransitionError(
            "Слаг арендатора: строчные латинские буквы/цифры/дефис/подчёркивание, 2-63 символа"
        )
