"""Сроки при утечке ПДн: правила без базы (152-ФЗ разд. 66.3, срез-207).

ЧТО НАШЛА СВЕРКА. Критерии приёмки 70.1 по ПДн выполнены — экспорт субъекта,
обезличивание, журнал доступа. Но поимённый разбор разд. 66 нашёл незакрытый
пункт 66.3: «Порядок при утечке: уведомление Роскомнадзора и субъектов **в
установленные сроки** — процедура incident response».

Этого не было ВООБЩЕ. Виды происшествий в продукте — про охрану труда
(несчастный случай, микротравма, «почти случилось», опасное условие). Утечки
персональных данных среди них нет: организации негде было про неё записать, и
некому считать срок.

ЗДЕСЬ ПРОВЕРЯЮТСЯ РЕШЕНИЯ:

1. **Сроки считаются от ОБНАРУЖЕНИЯ**, а не от самой утечки — так написано в
   законе, и разница бывает в недели.
2. **Часы, а не дни.** 24 и 72 часа — это срок со временем; округление до даты
   тихо дарит или отнимает часы там, где счёт идёт на часы.
3. **Три обязательства отмечаются по отдельности.** Уведомить регулятора,
   сообщить результаты расследования и уведомить людей — разные требования
   закона.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_privacy_breach.py -v``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.privacy.breach import (
    BREACH_STAGES,
    NOTIFY_REGULATOR_HOURS,
    REPORT_FINDINGS_HOURS,
    STAGE_TITLES,
    deadlines_for,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _stages(**overrides):
    payload = {
        "discovered_at": NOW - timedelta(hours=1),
        "regulator_notified_at": None,
        "findings_reported_at": None,
        "subjects_notified_at": None,
        "now": NOW,
    }
    payload.update(overrides)
    return {item.stage: item for item in deadlines_for(**payload)}


class TestСрокиИзЗакона:
    def test_сроки_двадцать_четыре_и_семьдесят_два_часа(self) -> None:
        assert NOTIFY_REGULATOR_HOURS == 24
        assert REPORT_FINDINGS_HOURS == 72

    def test_отсчёт_идёт_от_обнаружения(self) -> None:
        """ГЛАВНОЕ. Закон считает срок от момента ОБНАРУЖЕНИЯ, а не от момента
        самой утечки: между ними бывают недели."""

        discovered = NOW - timedelta(hours=5)
        stages = _stages(discovered_at=discovered)

        assert stages["notify_regulator"].due_at == discovered + timedelta(hours=24)
        assert stages["report_findings"].due_at == discovered + timedelta(hours=72)

    def test_просроченный_срок_назван_словами(self) -> None:
        stages = _stages(discovered_at=NOW - timedelta(hours=30))

        assert stages["notify_regulator"].status == "overdue"
        assert stages["notify_regulator"].status_title == "ПРОСРОЧЕНО"
        assert stages["report_findings"].status == "pending"

    def test_часы_округляются_вниз(self) -> None:
        """«Осталось 0 часов» честнее, чем «остался 1», когда на деле сорок
        минут: округление вверх подарило бы час, которого нет."""

        stages = _stages(discovered_at=NOW - timedelta(hours=23, minutes=20))

        assert stages["notify_regulator"].hours_left == 0
        assert stages["notify_regulator"].status == "pending"


class TestТриОбязательства:
    def test_их_ровно_три_и_у_каждого_подпись(self) -> None:
        assert len(BREACH_STAGES) == 3
        for stage in BREACH_STAGES:
            assert STAGE_TITLES[stage].strip()
            assert STAGE_TITLES[stage] != stage

    def test_выполненный_шаг_не_считается_просроченным(self) -> None:
        """Уведомление часто подают раньше, чем доходят руки до записи, —
        отметка задним числом не должна превращаться в просрочку."""

        discovered = NOW - timedelta(hours=30)
        stages = _stages(
            discovered_at=discovered,
            regulator_notified_at=discovered + timedelta(hours=5),
        )

        assert stages["notify_regulator"].status == "done"
        assert stages["notify_regulator"].status_title == "Выполнено"

    def test_отметка_одного_шага_не_закрывает_остальные(self) -> None:
        """ГЛАВНАЯ ТОНКОСТЬ: одна галочка на три обязательства означала бы, что
        выполнив лёгкое, организация считает закрытым и трудное."""

        stages = _stages(
            discovered_at=NOW - timedelta(hours=30),
            regulator_notified_at=NOW - timedelta(hours=29),
        )

        assert stages["notify_regulator"].status == "done"
        assert stages["report_findings"].status != "done"
        assert stages["notify_subjects"].status != "done"

    def test_у_уведомления_людей_срока_в_часах_нет_и_это_сказано(self) -> None:
        """Закон требует уведомить субъектов, но момент определяется
        обстоятельствами. Выдумать 24 часа значило бы выдать свою догадку за
        требование закона — поэтому состояние названо отдельным словом."""

        stages = _stages()

        assert stages["notify_subjects"].due_at is None
        assert stages["notify_subjects"].status == "no_deadline"
        assert "не задан" in stages["notify_subjects"].status_title


class TestБезМоментаОбнаружения:
    def test_срока_нет_пока_не_указано_когда_обнаружили(self) -> None:
        """Подставить «сейчас» значило бы сдвинуть отсчёт на время, прошедшее
        до записи, — и превратить просрочку в «срок идёт»."""

        stages = _stages(discovered_at=None)

        for stage in BREACH_STAGES:
            assert stages[stage].due_at is None
            assert stages[stage].status == "no_deadline"
