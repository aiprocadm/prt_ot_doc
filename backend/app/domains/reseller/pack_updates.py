"""Обновление эталонного набора у клиента (BIZ-52 срез-17, Доп. №1 разд. 52.3).

Последний пункт 52.3: «версионирование эталонов и приём обновлений без затирания
правок». Сегодня набор применяется ОДИН раз — при выдаче арендатора, — а дальше
эталон в репозитории живёт своей жизнью. Партнёр, добавивший в набор новую
опасность, донесёт её только до НОВЫХ клиентов; у прежних она не появится
никогда, и узнать об этом неоткуда.

**Сравниваем с применённым слепком, а не с текущими справочниками.** Это и есть
«без затирания правок»: строку, которую клиент осознанно удалил, приём
обновления НЕ воскресит — её нет среди новинок эталона, потому что она была в
применённой редакции. Сравнивай мы с состоянием справочников — каждое обновление
возвращало бы удалённое, и человек переставал бы нажимать кнопку.

**Редакция набора — отдельное число.** В файлах уже есть `version: "v1"`, но это
версия ФОРМАТА (и каталога `v1/`), а не редакция содержимого: подмени им номер
редакции — и первый же несовместимый формат сделает «обновление» бессмысленным.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.reseller.starter_pack import plan_starter_pack

#: Номер редакции по умолчанию: файлы, где его ещё не проставили, считаются
#: первой редакцией. Иначе добавление поля объявило бы все наборы обновлёнными.
DEFAULT_REVISION = 1


def revision_of(payload: dict | None) -> int:
    """Редакция набора. Отсутствие или мусор — первая."""

    if not isinstance(payload, dict):
        return DEFAULT_REVISION
    raw = payload.get("revision", DEFAULT_REVISION)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_REVISION
    return value if value > 0 else DEFAULT_REVISION


@dataclass(frozen=True)
class PackUpdate:
    """Что нового в эталоне по сравнению с применённым."""

    applied_revision: int
    current_revision: int
    #: Вид → названия, которых в применённой редакции не было.
    additions: dict[str, list[str]] = field(default_factory=dict)
    #: Слепка нет: арендатор выдан до появления учёта или набор не применялся.
    applied_unknown: bool = False

    @property
    def has_updates(self) -> bool:
        return any(self.additions.values())

    @property
    def summary(self) -> str:
        """Строка для человека.

        «Обновлений нет» и «сравнивать не с чем» — разные вещи, и путать их
        нельзя: во втором случае человек должен понимать, что предложенное —
        весь набор, а не разница.
        """

        if self.applied_unknown:
            if not self.has_updates:
                return "Эталон пуст: применять нечего"
            return (
                "Применённая редакция неизвестна — предложен весь набор целиком; "
                "уже заведённые строки повторно не создадутся"
            )
        if not self.has_updates:
            return f"Обновлений нет: применена редакция {self.applied_revision}"
        total = sum(len(values) for values in self.additions.values())
        return (
            f"Редакция {self.applied_revision} → {self.current_revision}: "
            f"новых строк {total}"
        )


def plan_pack_update(*, applied: dict | None, current: dict) -> PackUpdate:
    """Что предложить клиенту из новой редакции эталона.

    Только ДОБАВЛЕНИЯ. Удаление строк из эталона не превращается в удаление у
    клиента: он мог построить на них свою работу, а «обновление набора» не то
    действие, после которого данные исчезают.
    """

    current_plan = plan_starter_pack(current)
    applied_plan = plan_starter_pack(applied) if isinstance(applied, dict) else None

    additions: dict[str, list[str]] = {}
    for kind, names in current_plan.apply.items():
        known = (
            {name.casefold() for name in applied_plan.apply.get(kind, [])}
            if applied_plan is not None
            else set()
        )
        fresh = [name for name in names if name.casefold() not in known]
        if fresh:
            additions[kind] = fresh

    return PackUpdate(
        applied_revision=revision_of(applied) if applied_plan is not None else 0,
        current_revision=revision_of(current),
        additions=additions,
        applied_unknown=applied_plan is None,
    )
