"""BIZ-49 срез-2 (разд. 49.2): правила сводного «Центра внимания» по портфелю.

Чистые правила без БД. Смысл блока из ТЗ — «где просрочки, где не готов допуск,
у кого истекает обучение/медосмотр/СИЗ» ПО ВСЕМ клиентам сразу, поэтому здесь
решаются три вещи, которые нельзя отдать интерфейсу:

* **вес сигнала.** Десять неполных телефонов не важнее одного просроченного
  медосмотра: во втором случае человек не допущен к работе. Серьёзность клиента
  — это МАКСИМУМ по его сигналам, а не их сумма;
* **порядок портфеля.** Аутсорсер смотрит сверху вниз и до первой чашки кофе;
  «где горит сильнее» обязано быть первым, иначе список бесполезен;
* **честное «не смотрели».** У клиента со своим контуром данные лежат в другом
  арендаторе, и до делегированного доступа (разд. 49.3) мы их не читаем. Ноль
  в такой строке читался бы как «у клиента всё хорошо» — поэтому статус
  ``not_aggregated`` и ``total = None``, а не 0.

Просрочки ПБ (BIZ-54-57 срез-87, разд. 54.1) — один сигнал на все слагаемые
(перезарядка и поверка средств, тренировки, документы, противопожарные
инструктажи): в портфеле важно «у клиента горит по ПБ и сколько», а
расшифровку по слагаемым даёт светофор клиента (разд. 51.3), считающий те же
числа. Сигнал — факт, а не эталон: он есть и у клиента, чей модуль ПБ
выключен, если записи остались (срез-56).

Истёкшие удостоверения водителей (срез-88, разд. 54.1) — второй поимённый
сигнал того же ряда: считаются только допущенные к управлению
(``services/discipline_road_safety``, одно правило со светофором клиента и
календарём), вес — как у медосмотра, потому что водитель без действующего
удостоверения к работе не допущен.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

__all__ = [
    "AggregationStatus",
    "AttentionSignal",
    "ClientAttention",
    "SIGNAL_META",
    "Severity",
    "SignalKind",
    "build_client_attention",
    "not_aggregated",
    "sort_portfolio",
]


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        return _SEVERITY_WEIGHT[self]


_SEVERITY_WEIGHT: dict[Severity, int] = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class SignalKind(str, enum.Enum):
    MEDICAL_OVERDUE = "medical_overdue"
    PPE_OVERDUE = "ppe_overdue"
    TRAINING_OVERDUE = "training_overdue"
    CONTRACT_EXPIRING = "contract_expiring"
    CONTACTS_MISSING = "contacts_missing"
    FIRE_SAFETY_OVERDUE = "fire_safety_overdue"
    DRIVER_LICENSE_EXPIRED = "driver_license_expired"


class AggregationStatus(str, enum.Enum):
    AGGREGATED = "aggregated"
    NOT_AGGREGATED = "not_aggregated"


@dataclass(frozen=True)
class SignalMeta:
    severity: Severity
    title: str
    action_hint: str


#: Вес и человеческое имя каждого сигнала. Новый вид сигнала обязан появиться
#: здесь — иначе он молча уехал бы в конец списка с нулевым весом.
SIGNAL_META: dict[SignalKind, SignalMeta] = {
    SignalKind.MEDICAL_OVERDUE: SignalMeta(
        severity=Severity.CRITICAL,
        title="Просроченные медосмотры",
        action_hint="Направьте сотрудников на медосмотр: без него они не допущены к работе",
    ),
    # Истёкшее удостоверение допущенного водителя — как медосмотр: человек не
    # допущен к работе, и это не «нарушение к проверке», а остановка перевозок.
    SignalKind.DRIVER_LICENSE_EXPIRED: SignalMeta(
        severity=Severity.CRITICAL,
        title="Истёкшие водительские удостоверения",
        action_hint=(
            "Обновите удостоверение и срок в карточке водителя: с истёкшим "
            "к управлению не допускают"
        ),
    ),
    SignalKind.PPE_OVERDUE: SignalMeta(
        severity=Severity.HIGH,
        title="Просроченные СИЗ",
        action_hint="Выдайте СИЗ взамен просроченных",
    ),
    SignalKind.TRAINING_OVERDUE: SignalMeta(
        severity=Severity.HIGH,
        title="Просроченное обучение",
        action_hint="Проведите обучение или перенесите срок с обоснованием",
    ),
    SignalKind.CONTRACT_EXPIRING: SignalMeta(
        severity=Severity.HIGH,
        title="Истекает договор",
        action_hint="Продлите договор или согласуйте завершение ведения",
    ),
    # Просроченная перезарядка или истёкший ПТМ — нарушение к приходу МЧС,
    # но человека от работы не отстраняет: вес — как у СИЗ и обучения.
    SignalKind.FIRE_SAFETY_OVERDUE: SignalMeta(
        severity=Severity.HIGH,
        title="Просрочки по пожарной безопасности",
        action_hint=(
            "Перезарядите или поверьте средства защиты, проведите тренировки и "
            "противопожарные инструктажи, пересмотрите документы"
        ),
    ),
    SignalKind.CONTACTS_MISSING: SignalMeta(
        severity=Severity.LOW,
        title="Неполные контакты сотрудников",
        action_hint="Заполните email и телефон — без них не доходят уведомления",
    ),
}


@dataclass(frozen=True)
class AttentionSignal:
    kind: SignalKind
    count: int
    severity: Severity
    title: str
    action_hint: str


@dataclass(frozen=True)
class ClientAttention:
    client_id: str
    client_name: str
    aggregation: AggregationStatus
    signals: list[AttentionSignal] = field(default_factory=list)
    #: Сумма сигналов; ``None`` — данные не собирались (см. ``not_aggregated``).
    total: int | None = 0
    severity: Severity | None = None
    reason: str | None = None


def build_client_attention(
    *,
    client_id: str,
    client_name: str,
    counts: dict[SignalKind, int],
    contract_expiring: bool,
) -> ClientAttention:
    """Собрать строку портфеля из посчитанных сигналов клиента."""

    raw = dict(counts)
    if contract_expiring:
        raw[SignalKind.CONTRACT_EXPIRING] = raw.get(SignalKind.CONTRACT_EXPIRING, 0) + 1

    signals = [
        AttentionSignal(
            kind=kind,
            count=count,
            severity=SIGNAL_META[kind].severity,
            title=SIGNAL_META[kind].title,
            action_hint=SIGNAL_META[kind].action_hint,
        )
        for kind, count in raw.items()
        if count > 0
    ]
    # Сначала тяжёлые, при равном весе — где больше людей затронуто.
    signals.sort(key=lambda s: (-s.severity.weight, -s.count, s.kind.value))

    return ClientAttention(
        client_id=client_id,
        client_name=client_name,
        aggregation=AggregationStatus.AGGREGATED,
        signals=signals,
        total=sum(s.count for s in signals),
        severity=signals[0].severity if signals else None,
    )


def not_aggregated(*, client_id: str, client_name: str, reason: str) -> ClientAttention:
    """Строка клиента, чьи данные в этом срезе не читаются (свой контур)."""

    return ClientAttention(
        client_id=client_id,
        client_name=client_name,
        aggregation=AggregationStatus.NOT_AGGREGATED,
        signals=[],
        total=None,
        severity=None,
        reason=reason,
    )


def _sort_key(row: ClientAttention) -> tuple[int, int, str]:
    if row.aggregation is AggregationStatus.NOT_AGGREGATED:
        # «Не смотрели» — это работа, а не спокойствие: выше чистых, ниже горящих.
        return (0, 0, row.client_name)
    weight = row.severity.weight if row.severity else -1
    return (-weight, -(row.total or 0), row.client_name)


def sort_portfolio(rows: list[ClientAttention]) -> list[ClientAttention]:
    """Портфель сверху вниз: где горит сильнее — первым."""

    return sorted(rows, key=_sort_key)
