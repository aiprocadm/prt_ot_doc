"""Сравнение редакций акта: «текста нет» ≠ «изменений нет» (срез-202).

ЧТО БЫЛО. Разд. 19.4 требует «черновик → публикация → ДИФФ → уведомления →
задачи на пересмотр → контроль завершения». Пять шагов из шести работали
(срезы 141, 144, 198), а дифф был невозможен по построению: ``NpaRevision``
хранил только ``change_summary`` — одну фразу, — а пункты принадлежали акту.
Система знала, ЧТО редакция есть, и не знала, чем она отличается.

ГЛАВНОЕ, ЧТО ЗДЕСЬ ЗАКРЕПЛЕНО, — НЕ САМО СРАВНЕНИЕ, А ЧЕСТНЫЙ ОТКАЗ.

У всех редакций, заведённых до этого среза, текста нет. Соблазн выдать на них
«изменений нет» (пустой список против пустого) или «всё добавлено» (пустой
против полного) очень велик: оба ответа выглядят как работа. Оба — ложь того же
класса, что срез-197 вылавливал у сводки влияния, где отсутствие строки
читалось как «этот закон вас не задевает».

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_npa_revision_diff.py -v``.
"""

from __future__ import annotations

from app.domains.npa.revision_diff import (
    CHANGE_TITLES,
    NO_TEXT_REASON,
    diff_clauses,
    normalize_text,
)


class TestЧестныйОтказ:
    def test_без_снимка_отвечаем_не_можем_а_не_пусто(self) -> None:
        """ГЛАВНАЯ ПРОВЕРКА СРЕЗА."""

        result = diff_clauses(None, {"п. 1": "Текст"})

        assert result.comparable is False
        assert result.reason == NO_TEXT_REASON
        assert result.changes == ()
        # И «всё добавлено» тоже не отвечаем: мы не знаем, что было раньше.
        assert result.as_dict()["summary"]["added"] == 0

    def test_обе_без_снимка_это_тоже_отказ(self) -> None:
        result = diff_clauses(None, None)

        assert result.comparable is False
        assert result.reason == NO_TEXT_REASON

    def test_пустой_снимок_это_НЕ_отсутствие_снимка(self) -> None:
        """Редакция без пунктов — законное состояние (текст ведут одним
        документом). Сравнить её можно, и ответ «изменений нет» здесь ЧЕСТЕН."""

        result = diff_clauses({}, {})

        assert result.comparable is True
        assert result.reason == ""
        assert result.changes == ()

    def test_причина_отказа_словами_а_не_кодом(self) -> None:
        assert "не заносили" in NO_TEXT_REASON
        assert NO_TEXT_REASON != "no_text"


class TestСравнение:
    def test_добавленный_исключённый_и_изменённый(self) -> None:
        before = {"п. 1": "Общие положения", "п. 2": "Старый порядок", "п. 3": "Исключат"}
        after = {"п. 1": "Общие положения", "п. 2": "Новый порядок", "п. 4": "Новое"}

        result = diff_clauses(before, after)

        assert result.comparable is True
        by_code = {c.code: c for c in result.changes}
        assert by_code["п. 2"].change == "modified"
        assert by_code["п. 2"].before == "Старый порядок"
        assert by_code["п. 2"].after == "Новый порядок"
        assert by_code["п. 3"].change == "removed"
        assert by_code["п. 4"].change == "added"
        # Неизменённое в список НЕ попадает, но и не теряется — оно посчитано.
        assert "п. 1" not in by_code
        assert result.unchanged == 1

    def test_пункты_сопоставляются_по_коду_а_не_по_порядку(self) -> None:
        """Порядок в акте сам по себе смысла не несёт, а коды несут: именно на
        код ссылается требование реестра."""

        before = {"п. 1": "А", "п. 2": "Б"}
        after = {"п. 2": "Б", "п. 1": "А"}

        assert diff_clauses(before, after).changes == ()

    def test_изменения_идут_по_порядку_кода(self) -> None:
        """Дифф читают сверху вниз; прыгающий порядок заставил бы искать глазами."""

        result = diff_clauses({}, {"п. 3": "в", "п. 1": "а", "п. 2": "б"})

        assert [c.code for c in result.changes] == ["п. 1", "п. 2", "п. 3"]

    def test_у_каждого_изменения_есть_подпись_словами(self) -> None:
        result = diff_clauses({"п. 1": "а"}, {"п. 1": "б"})

        row = result.changes[0].as_dict()
        assert row["change_title"] == "Текст изменён"
        assert row["change_title"] != row["change"]
        for code, title in CHANGE_TITLES.items():
            assert title.strip() and title != code


class TestШумПриПереносе:
    def test_лишние_пробелы_не_считаются_правкой(self) -> None:
        """Пункт, перенесённый из документа второй раз, часто отличается только
        двойными пробелами и переносами строк. Показать это как «текст изменён»
        значит утопить настоящие правки в шуме — и на третий раз человек
        перестанет открывать дифф вовсе."""

        before = {"п. 1": "Обучение  проводится\nне реже раза в год"}
        after = {"п. 1": "Обучение проводится не реже раза в год"}

        assert diff_clauses(before, after).changes == ()

    def test_показываем_исходный_текст_а_не_схлопнутый(self) -> None:
        """Схлопывание — приём СРАВНЕНИЯ. Обрезать пользовательские данные при
        показе нельзя: человек должен видеть то, что занесли."""

        before = {"п. 1": "Первый\n\nабзац"}
        after = {"п. 1": "Другой текст"}

        change = diff_clauses(before, after).changes[0]
        assert change.before == "Первый\n\nабзац"

    def test_настоящая_правка_внутри_шума_не_теряется(self) -> None:
        before = {"п. 1": "не реже  раза в год"}
        after = {"п. 1": "не реже раза в  полгода"}

        assert diff_clauses(before, after).changes[0].change == "modified"

    def test_схлопывание_не_склеивает_слова(self) -> None:
        assert normalize_text("а\nб") == "а б"
        assert normalize_text("  а  б  ") == "а б"
