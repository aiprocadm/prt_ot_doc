"""Третий шаг мастера для сценариев каталога (Доп. №1, разд. 50.2).

ТЗ: «Предпросмотр состава и readiness — что войдёт в комплект, Document
Readiness Score, чего не хватает и почему, какие формы будут сгенерированы».

Такой шаг в коде был — но только для ДРУГОГО контура: пакетной генерации по
таблице (``analyze_pack_readiness``, вход — колонки и строки источника). Мастер
разового комплекта работает не с таблицей, а со сценарием каталога, площадкой и
списком людей, и предпросмотра у него не было вовсе.

Цена отсутствия: единственный способ узнать, что чего-то не хватает, — запустить
генерацию. Все проверки генерации падают на ПЕРВОЙ же причине (нет компании →
404, нет площадки → 404, человек из другой компании → 400), поэтому пять
пропущенных сведений чинились пятью запусками. Здесь причины собираются СПИСКОМ.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.packs.fields import expand_answers, questions_for
from app.domains.packs.readiness import ReadinessProblem

__all__ = [
    "PreviewDocument",
    "ScenarioPreview",
    "analyze_scenario_readiness",
]

#: Сколько имён показываем поимённо в одной проблеме. Остальные — числом.
#: Список из трёхсот человек в сообщении об ошибке нечитаем.
NAMES_LIMIT = 20


@dataclass(frozen=True)
class PreviewDocument:
    """Одна форма, которая выйдет из генерации."""

    template_name: str
    #: Для кого. ``None`` — документ на организацию целиком (приказ, перечень).
    person_name: str | None = None


@dataclass(frozen=True)
class ScenarioPreview:
    """Ответ третьего шага мастера для сценария каталога."""

    ready: bool
    #: Доля людей, которые дадут полный комплект, в процентах.
    #: Без людей — 100, если нет пустых обязательных полей.
    score: int
    documents_total: int
    persons_total: int
    persons_ready: int
    documents: tuple[PreviewDocument, ...] = field(default_factory=tuple)
    problems: tuple[ReadinessProblem, ...] = field(default_factory=tuple)


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _named(names: list[str]) -> str:
    shown = ", ".join(names[:NAMES_LIMIT])
    if len(names) > NAMES_LIMIT:
        return f"{shown} и ещё {len(names) - NAMES_LIMIT}"
    return shown


def analyze_scenario_readiness(
    *,
    pack_code: str,
    templates: list[str],
    answers: dict[str, object],
    company_name: str | None,
    site_name: str | None,
    site_required: bool = False,
    person_names: list[str],
    persons_without_position: list[str] | None = None,
    missing_person_ids: list[str] | None = None,
    foreign_person_names: list[str] | None = None,
) -> ScenarioPreview:
    """Собрать ВСЕ причины, по которым комплект выйдет не таким, как ждут.

    Вход намеренно примитивный (имена и списки, а не модели ORM): разбор того,
    «что не так», не должен зависеть от того, как именно загружены данные, и
    проверяется без базы.

    Блокирующее отделено от предупреждений: нет организации — генерации не
    будет; не заполнено необязательное поле — комплект выйдет, но с пробелом в
    этом месте. Смешивать их значит либо пугать пустяками, либо прятать
    настоящий затор.
    """

    problems: list[ReadinessProblem] = []
    missing_ids = list(missing_person_ids or [])
    foreign = list(foreign_person_names or [])
    no_position = list(persons_without_position or [])

    if _blank(company_name):
        problems.append(
            ReadinessProblem(
                code="COMPANY_MISSING",
                message="Не выбрана организация клиента — без неё документы не на кого оформить.",
                blocking=True,
            )
        )
    if site_required and _blank(site_name):
        problems.append(
            ReadinessProblem(
                code="SITE_MISSING",
                message="Сценарий про объект, а объект не выбран.",
                blocking=True,
            )
        )
    if not templates:
        problems.append(
            ReadinessProblem(
                code="PACK_EMPTY",
                message=(f"В комплекте «{pack_code}» нет ни одного шаблона — генерировать нечего."),
                blocking=True,
            )
        )
    if missing_ids:
        problems.append(
            ReadinessProblem(
                code="PERSONS_NOT_FOUND",
                message=(
                    "Не найдены сотрудники: "
                    f"{_named(missing_ids)}. Возможно, их удалили или это чужие записи."
                ),
                blocking=True,
                rows_total=len(missing_ids),
            )
        )
    if foreign:
        problems.append(
            ReadinessProblem(
                code="PERSONS_FOREIGN",
                message=(
                    f"Сотрудники другой организации: {_named(foreign)}. "
                    "Комплект оформляется по одной организации."
                ),
                blocking=True,
                rows_total=len(foreign),
            )
        )

    # Обязательные поля сценария — из объявления (срез-4), а не из памяти:
    # список вопросов и список проверяемых полей обязаны совпадать.
    expanded = expand_answers(answers or {})
    blank_required: list[str] = []
    blank_optional: list[str] = []
    for question in questions_for(pack_code):
        if not _blank(expanded.get(question.name)):
            continue
        (blank_required if question.required else blank_optional).append(question.label)
    if blank_required:
        problems.append(
            ReadinessProblem(
                code="REQUIRED_FIELDS_BLANK",
                message=f"Не заполнено обязательное: {_named(blank_required)}.",
                blocking=True,
                rows_total=len(blank_required),
            )
        )
    if blank_optional:
        problems.append(
            ReadinessProblem(
                code="OPTIONAL_FIELDS_BLANK",
                message=(
                    f"Останется пустым в документах: {_named(blank_optional)}. "
                    "Это допустимо, но проверьте, что так и задумано."
                ),
                blocking=False,
                rows_total=len(blank_optional),
            )
        )

    if no_position:
        problems.append(
            ReadinessProblem(
                code="PERSONS_WITHOUT_POSITION",
                message=(
                    f"Без должности: {_named(no_position)}. "
                    "В документах графа должности останется пустой."
                ),
                blocking=False,
                rows_total=len(no_position),
            )
        )

    documents = tuple(
        PreviewDocument(template_name=template, person_name=person)
        for person in (person_names or [None])
        for template in templates
    )

    persons_total = len(person_names)
    persons_ready = max(persons_total - len(no_position), 0)
    blocking = any(problem.blocking for problem in problems)
    if persons_total:
        score = round(persons_ready * 100 / persons_total)
    else:
        # Без людей «готовность» — это про поля: пусто в необязательном тоже
        # снижает качество комплекта, но не мешает его собрать.
        score = 100 if not blank_optional else 50
    if blocking:
        # Блокирующая причина обнуляет готовность: «85 %» рядом с «генерация
        # невозможна» читается как «почти готово» и вводит в заблуждение.
        score = 0

    return ScenarioPreview(
        ready=not blocking,
        score=score,
        documents_total=len(documents),
        persons_total=persons_total,
        persons_ready=persons_ready,
        documents=documents,
        problems=tuple(problems),
    )
