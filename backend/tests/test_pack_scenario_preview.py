"""BIZ-50 срез-6 — третий шаг мастера для сценариев каталога. Без БД.

ТЗ разд. 50.2: «Предпросмотр состава и readiness — что войдёт в комплект,
Document Readiness Score, чего не хватает и почему, какие формы будут
сгенерированы».

Такой шаг был только для ДРУГОГО контура — пакетной генерации по таблице. У
мастера разового комплекта предпросмотра не было: единственный способ узнать,
чего не хватает, — запустить генерацию, а она падает на ПЕРВОЙ же причине.
"""

from __future__ import annotations

from app.modules.packs.scenario_preview import NAMES_LIMIT, analyze_scenario_readiness

SCENARIO = "OT_NEW_EMPLOYEE"


def _answers(**overrides: object) -> dict[str, object]:
    """Полные ответы на вопросы сценария — база, от которой отнимают."""

    from app.modules.packs.fields import questions_for

    return {question.name: "заполнено" for question in questions_for(SCENARIO)} | overrides


def _preview(**overrides: object):
    kwargs: dict[str, object] = {
        "pack_code": SCENARIO,
        "templates": ["Приказ", "Инструкция"],
        "answers": _answers(),
        "company_name": "ООО Ромашка",
        "site_name": None,
        "person_names": ["Иванов Иван"],
    }
    kwargs.update(overrides)
    return analyze_scenario_readiness(**kwargs)  # type: ignore[arg-type]


def _codes(preview) -> set[str]:
    return {problem.code for problem in preview.problems}


def test_all_reasons_come_at_once() -> None:
    """Главное в срезе: причины СПИСКОМ, а не по одной за запуск.

    Генерация падает на первой же: нет организации → 404, и про остальное
    узнаёшь только после того, как починишь первое.
    """

    preview = _preview(
        company_name=None,
        templates=[],
        answers={},
        missing_person_ids=["нет-такого"],
    )

    assert preview.ready is False
    assert {
        "COMPANY_MISSING",
        "PACK_EMPTY",
        "PERSONS_NOT_FOUND",
        "REQUIRED_FIELDS_BLANK",
    } <= _codes(preview)


def test_blocking_is_separated_from_warnings() -> None:
    """Смешать значит либо пугать пустяками, либо прятать настоящий затор."""

    preview = _preview(persons_without_position=["Иванов Иван"])

    assert preview.ready is True, "пустая должность не мешает собрать комплект"
    problem = next(p for p in preview.problems if p.code == "PERSONS_WITHOUT_POSITION")
    assert problem.blocking is False


def test_required_fields_come_from_the_declaration() -> None:
    """Список вопросов и список проверяемых полей обязаны совпадать.

    Разойдутся — мастер спросит одно, а предпросмотр потребует другое.
    """

    from app.modules.packs.fields import questions_for

    required = [q for q in questions_for(SCENARIO) if q.required]
    assert required, "у сценария нет обязательных полей — тест бессмысленен"

    preview = _preview(answers=_answers(**{required[0].name: "   "}))

    problem = next(p for p in preview.problems if p.code == "REQUIRED_FIELDS_BLANK")
    assert problem.blocking is True
    assert required[0].label in problem.message, "не сказано, ЧТО именно заполнить"


def test_blank_optional_is_named_but_does_not_block() -> None:
    """«Останется пустым» — это предупреждение, а не запрет."""

    from app.modules.packs.fields import questions_for

    optional = [q for q in questions_for(SCENARIO) if not q.required]
    assert optional, "у сценария нет необязательных полей — тест бессмысленен"

    preview = _preview(answers=_answers(**{optional[0].name: ""}))

    assert preview.ready is True
    assert "OPTIONAL_FIELDS_BLANK" in _codes(preview)


def test_documents_are_listed_per_person() -> None:
    """«Какие формы будут сгенерированы» — это список, а не число."""

    preview = _preview(person_names=["Иванов Иван", "Петров Пётр"])

    assert preview.documents_total == 4  # 2 шаблона × 2 человека
    assert {doc.person_name for doc in preview.documents} == {"Иванов Иван", "Петров Пётр"}
    assert {doc.template_name for doc in preview.documents} == {"Приказ", "Инструкция"}


def test_pack_without_persons_lists_org_level_documents() -> None:
    """Приказ по организации оформляется не на человека — и это не ошибка."""

    preview = _preview(person_names=[])

    assert preview.documents_total == 2
    assert all(doc.person_name is None for doc in preview.documents)
    assert preview.ready is True


def test_blocking_zeroes_the_score() -> None:
    """«85 %» рядом с «генерация невозможна» читается как «почти готово»."""

    preview = _preview(person_names=["Иванов Иван"], company_name=None)

    assert preview.ready is False
    assert preview.score == 0


def test_score_counts_people_who_give_a_full_set() -> None:
    preview = _preview(
        person_names=["А", "Б", "В", "Г"],
        persons_without_position=["Г"],
    )

    assert preview.persons_total == 4
    assert preview.persons_ready == 3
    assert preview.score == 75


def test_long_lists_are_summarised() -> None:
    """Список из трёхсот имён в сообщении нечитаем."""

    names = [f"Сотрудник {index}" for index in range(NAMES_LIMIT + 5)]
    preview = _preview(person_names=names, persons_without_position=names)

    problem = next(p for p in preview.problems if p.code == "PERSONS_WITHOUT_POSITION")
    assert "и ещё 5" in problem.message
    assert problem.rows_total == len(names), "число затронутых потеряно"


def test_foreign_person_is_blocking_and_named() -> None:
    """Комплект оформляется по одной организации — чужой человек это ломает."""

    preview = _preview(foreign_person_names=["Сидоров Сидор"])

    problem = next(p for p in preview.problems if p.code == "PERSONS_FOREIGN")
    assert problem.blocking is True
    assert "Сидоров Сидор" in problem.message
