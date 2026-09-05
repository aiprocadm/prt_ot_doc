"""BIZ-54-57 срез-4: библиотека предустановленных правил (Доп. №1 разд. 57.3).

Приёмка §58.3: «Для каждой дисциплины есть библиотека предустановленных правил
(starter-pack)».

ГЛАВНЫЙ СТОРОЖ ЗДЕСЬ — не «правил столько-то», а **каждое правило библиотеки
принимается самим движком**: событие существует, поля условий есть в payload
этого события, действия проходят валидацию. Библиотека, которую движок не
примет, не сработает НИКОГДА — и это худший вид «поставленной экспертизы»:
специалист уверен, что система его страхует, а она молчит.
"""

from __future__ import annotations

import pytest

from app.core.disciplines import Discipline
from app.domains.rules_library.library import (
    DISCIPLINES_WITHOUT_RULES,
    LIBRARY_RULES,
    coverage,
    rules_for,
)
from app.modules.rules_engine import actions as actions_mod
from app.modules.rules_engine import conditions as conditions_mod
from app.services.events import _PAYLOADS, EventType

_EVENTS = {event.value: event for event in EventType}


class TestДвижокПриметКаждоеПравило:
    """Без этого набора библиотека могла бы молчать при полном порядке на вид."""

    @pytest.mark.parametrize("rule", LIBRARY_RULES, ids=lambda r: r.name)
    def test_событие_правила_существует(self, rule) -> None:
        assert rule.event_type in _EVENTS, rule.name

    @pytest.mark.parametrize("rule", LIBRARY_RULES, ids=lambda r: r.name)
    def test_условия_проходят_разбор_движка(self, rule) -> None:
        """Поля условий сверяются с payload ИМЕННО ЭТОГО события.

        Опечатка в имени поля дала бы правило, которое не срабатывает никогда и
        при этом выглядит настроенным.
        """

        fields = frozenset(_PAYLOADS[_EVENTS[rule.event_type]].model_fields)
        conditions_mod.validate_conditions(rule.conditions, known_fields=fields)

    @pytest.mark.parametrize("rule", LIBRARY_RULES, ids=lambda r: r.name)
    def test_действия_проходят_разбор_движка(self, rule) -> None:
        actions_mod.validate_actions(rule.actions)

    @pytest.mark.parametrize("rule", LIBRARY_RULES, ids=lambda r: r.name)
    def test_у_правила_есть_действие(self, rule) -> None:
        """Правило без действий — тишина, выданная за автоматизацию."""

        assert rule.actions, rule.name

    @pytest.mark.parametrize("rule", LIBRARY_RULES, ids=lambda r: r.name)
    def test_подстановки_берут_поля_этого_события(self, rule) -> None:
        """Шаблон вида {item_name} обязан ссылаться на поле payload события.

        Иначе в задаче окажется пустое место там, где специалист ждёт название
        СИЗ или номер наряда.
        """

        import re

        fields = set(_PAYLOADS[_EVENTS[rule.event_type]].model_fields)
        for action in rule.actions:
            for key, value in action.items():
                if not key.endswith("_template") or not isinstance(value, str):
                    continue
                for name in re.findall(r"\{([A-Za-z0-9_.]+)\}", value):
                    assert name.split(".")[0] in fields, f"{rule.name}: {name}"


class TestИменаУникальны:
    def test_имена_не_повторяются(self) -> None:
        """Посев идемпотентен ПО ИМЕНИ — дубль имени сломал бы идемпотентность."""

        names = [rule.name for rule in LIBRARY_RULES]
        assert len(names) == len(set(names))


class TestПокрытиеДисциплин:
    def test_каждая_дисциплина_либо_с_правилами_либо_с_причиной(self) -> None:
        """Ноль без объяснения читается как «забыли», а не как решение."""

        for row in coverage():
            assert row["rules"] > 0 or row["reason"].strip(), row["discipline"]

    def test_в_покрытии_ВСЕ_дисциплины_тз(self) -> None:
        assert {row["discipline"] for row in coverage()} == {d.value for d in Discipline}

    def test_причины_только_у_дисциплин_без_правил(self) -> None:
        """Сторож против протухшей причины: появились правила — причина уходит."""

        for discipline in DISCIPLINES_WITHOUT_RULES:
            assert not rules_for(discipline), discipline.value

    def test_причина_говорит_о_событиях_а_не_о_сущностях(self) -> None:
        """Сторож против протухшей причины ВТОРОГО рода.

        Прошлый сторож проверял, что причина ЕСТЬ, но не проверял, что она
        правдива. Причина экологии полгода утверждала, что «объектов НВОС и
        отходов в продукте нет», хотя они появились ещё на срезе-1: довод про
        СУЩНОСТИ протухает при первом же новом реестре. Правило подписывается
        на СОБЫТИЕ — только про них причина и может говорить честно.
        """

        for discipline, reason in DISCIPLINES_WITHOUT_RULES.items():
            assert "событ" in reason.lower(), discipline.value

    def test_дисциплины_нарядов_допусков_покрыты(self) -> None:
        """Ради них в этом срезе и заведено событие о выдаче наряда."""

        assert rules_for(Discipline.FIRE_SAFETY)
        assert rules_for(Discipline.INDUSTRIAL_SAFETY)

    def test_правила_нарядов_различают_вид_работ(self) -> None:
        """Разметка среза-3: огневые — ПБ, газоопасные — ПромБез.

        Без условия по виду работ оба правила срабатывали бы на любом наряде, и
        «дисциплина» на карточке стала бы украшением.
        """

        for discipline, work_type in (
            (Discipline.FIRE_SAFETY, "hot_work"),
            (Discipline.INDUSTRIAL_SAFETY, "gas_hazardous"),
        ):
            rule = rules_for(discipline)[0]
            assert rule.event_type == "WorkPermitIssued"
            assert rule.conditions["conditions"] == [
                {"field": "work_type", "op": "eq", "value": work_type}
            ]


class TestСрокиДисциплин:
    """Срез-62: событие «срок дисциплины просрочен» закрыло три пустые клетки."""

    def test_у_каждой_дисциплины_есть_правило(self) -> None:
        """Приёмка §58.3 буквально: «для КАЖДОЙ дисциплины есть библиотека»."""

        for discipline in Discipline:
            assert rules_for(discipline), discipline.value
        assert not DISCIPLINES_WITHOUT_RULES

    def test_бывшие_пустые_клетки_висят_на_событии_сроков(self) -> None:
        """Экология, ГО и ЧС, БДД получили правила ровно на новом событии —
        не на свободном тексте и не на чужом событии."""

        for discipline in (
            Discipline.ECOLOGY,
            Discipline.CIVIL_DEFENSE,
            Discipline.ROAD_SAFETY,
        ):
            for rule in rules_for(discipline):
                assert rule.event_type == "DisciplineDeadlineOverdue", rule.name

    def test_правила_сроков_различают_источник(self) -> None:
        """Одно событие на все сроки — значит, правило обязано сказать, ЧЕЙ
        срок: без условия по источнику «отстранить водителя» срабатывало бы
        на просроченный замер ПЭК."""

        from app.services.discipline_deadline_events import DEADLINE_EVENT_SOURCES

        seen: set[str] = set()
        for rule in LIBRARY_RULES:
            if rule.event_type != "DisciplineDeadlineOverdue":
                continue
            conditions = rule.conditions["conditions"]
            assert len(conditions) == 1 and conditions[0]["field"] == "source_type", rule.name
            source = conditions[0]["value"]
            assert source in DEADLINE_EVENT_SOURCES, rule.name
            seen.add(source)
        # каждый обходимый источник закрыт правилом — иначе событие есть, а
        # экспертизы по нему нет
        assert seen == set(DEADLINE_EVENT_SOURCES)
