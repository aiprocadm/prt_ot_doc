"""Контур ГО и ЧС срез-3 (Доп. №1 разд. 56.1): комиссии КЧС и эвакокомиссия.

Требование: «Комиссии: КЧС и ПБ, эвакокомиссия — составы, приказы, протоколы,
решения».

СВЕРКА (найдено срезом-2, закрывается здесь). Контур комиссий в продукте
СУЩЕСТВУЕТ ЦЕЛИКОМ: ``Committee`` со составами (``CommitteeMember``),
заседаниями (``CommitteeMeeting``), повестками, протоколами, решениями
(``CommitteeDecision``), задачами по решениям и голосами. Не хватало ровно
двух значений закрытого словаря ``CommitteeKind``: комиссии по чрезвычайным
ситуациям и обеспечению пожарной безопасности (КЧС и ПБ) и эвакуационной
комиссии. Требование ТЗ упиралось В СЛОВАРЬ, а не в новый контур.

Решения:

* **два значения словаря, а НЕ новый реестр комиссий ГО.** Дублировать
  составы, протоколы и решения ради дисциплины — прямое нарушение принципа
  мультидисциплинарности (преамбула разд. 54): ядро не дублируется, дисциплина
  добавляет только своё. Своего у комиссии ГО ровно одно — её вид;
* **расширение нативного enum PG отдельной миграцией** с ``autocommit_block``
  и ``ADD VALUE IF NOT EXISTS`` (прецедент wa03): PG запрещает использовать
  новое значение в той же транзакции, где оно добавлено. Удаление значения при
  откате НЕВОЗМОЖНО — задокументировано как односторонний шаг;
* **сторож против дрейфа подписей.** Подписи видов комиссий на фронте
  написаны РУКАМИ (``KIND_LABELS`` в CommitteesPage.tsx), и добавление
  значения на бэкенде их не обновляет: в списке появился бы сырой код
  ``commission_emergency``, а завести такую комиссию было бы нельзя вовсе —
  выпадающий список строится из того же map. Ровно этот класс дрейфа уже
  ловился в календаре (``medical_referral``, срез экокалендаря), поэтому здесь
  сразу ставится тест-сторож.

ГРАНИЦА: платформа НЕ решает, обязана ли организация создавать КЧС или
эвакокомиссию — это следует из категории организации по ГО и решений органа
управления ГОЧС. Словарь лишь даёт назвать вид уже созданной комиссии.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.committees import CommitteeKind
from app.schemas.committees import CommitteeCreate

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMITTEES_PAGE = (
    _REPO_ROOT / "frontend" / "src" / "pages" / "committees" / "CommitteesPage.tsx"
)


class TestСловарьВидов:
    def test_кчс_и_эвакокомиссия_в_словаре(self) -> None:
        """Требование 56.1 «Комиссии: КЧС и ПБ, эвакокомиссия»."""

        values = {member.value for member in CommitteeKind}
        assert "commission_emergency" in values
        assert "commission_evacuation" in values

    def test_прежние_виды_не_переименованы(self) -> None:
        """Значения — ключи в БД у арендаторов: переименование их осиротит."""

        values = {member.value for member in CommitteeKind}
        assert {
            "osms",
            "pb",
            "commission_training",
            "commission_investigation",
            "other",
        } <= values

    def test_новых_реестров_комиссий_не_заведено(self) -> None:
        """Мультидисциплинарность: ядро не дублируется.

        Комиссия ГО — это вид комиссии, а не отдельная сущность: составы,
        протоколы и решения уже есть в контуре committees.
        """

        models_dir = _REPO_ROOT / "backend" / "app" / "models"
        forbidden = ("cd_committee", "civil_defense_committee", "evacuation_committee")
        for path in models_dir.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in forbidden:
                assert name not in text, f"{path.name}: завёлся дубль {name}"


class TestСхемыПринимаютНовыеВиды:
    @pytest.mark.parametrize(
        "kind", ["commission_emergency", "commission_evacuation"]
    )
    def test_комиссия_заводится_с_новым_видом(self, kind: str) -> None:
        payload = CommitteeCreate(kind=kind, name="Комиссия")
        assert payload.kind.value == kind

    def test_неизвестный_вид_отвергается(self) -> None:
        with pytest.raises(ValidationError):
            CommitteeCreate(kind="комиссия по чему-нибудь", name="Комиссия")

    def test_вид_обязателен(self) -> None:
        with pytest.raises(ValidationError):
            CommitteeCreate(name="Комиссия без вида")  # type: ignore[call-arg]


class TestМиграцияРасширенияEnum:
    """Проверяем МОДУЛЬ миграции, а не её текст.

    Первая редакция этих тестов грепала исходник и падала на собственном
    пояснении в докстринге — грепу всё равно, объяснение это или код.
    """

    def _module(self):
        path = (
            _REPO_ROOT
            / "backend"
            / "app"
            / "migrations"
            / "versions"
            / "20260827_cd04_committee_kinds.py"
        )
        assert path.exists(), "миграция расширения committeekind не найдена"
        spec = importlib.util.spec_from_file_location("cd04_mig", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_добавляются_ровно_два_значения(self) -> None:
        assert set(self._module()._NEW_VALUES) == {
            "commission_emergency",
            "commission_evacuation",
        }

    def test_шаг_идемпотентен_и_вне_транзакции(self) -> None:
        """IF NOT EXISTS — повторный накат не падает; autocommit — требование PG."""

        source = inspect.getsource(self._module().upgrade)
        assert "ADD VALUE IF NOT EXISTS" in source
        assert "autocommit_block" in source

    def test_на_sqlite_шаг_пропускается(self) -> None:
        """У SQLite нет нативных enum — колонка ведёт себя как TEXT."""

        source = inspect.getsource(self._module().upgrade)
        assert 'dialect.name != "postgresql"' in source

    def test_откат_ничего_не_выполняет(self) -> None:
        """PG не умеет DROP VALUE: односторонний шаг, откат пустой."""

        source = inspect.getsource(self._module().downgrade)
        assert "op.execute" not in source
        assert "ALTER TYPE" not in source


class TestСторожПодписейНаФронте:
    """Сторож против дрейфа: подписи видов на фронте написаны руками.

    Добавление значения на бэкенде их не обновляет — в списке появился бы
    сырой код, а завести комиссию нового вида было бы нельзя вовсе
    (выпадающий список строится из того же map). Тот же класс дрейфа, что
    ``medical_referral`` в источниках календаря.
    """

    def test_подписи_покрывают_все_виды_из_бэкенда(self) -> None:
        text = _COMMITTEES_PAGE.read_text(encoding="utf-8")
        block = re.search(
            r"KIND_LABELS:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}", text, re.S
        )
        assert block is not None, "не нашёлся map KIND_LABELS"
        front = set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))
        backend = {member.value for member in CommitteeKind}
        assert front == backend, sorted(front ^ backend)
