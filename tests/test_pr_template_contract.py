"""SEC-69 (Доп. №3 разд. 69.3): Security DoD — «седьмой вопрос» в ревью.

ТЗ: «Security Definition of Done: к шести вопросам разд. 21 добавить седьмой —
"какие новые поверхности атаки вводит фича и как они закрыты?"». Владелец
делегировал решение — вопрос введён в PR-шаблон.

**Что нашла сверка.** Константа ``SECURITY_QUESTION`` существовала в
``product_spec.py`` и не читалась НИКЕМ: вопрос был записан и ни на что не
влиял — ровно тот же дефект «написано, но никогда не читается», что был у
``UX_BUDGET`` до BIZ-59 среза-1.

**Приём тот же, что у бюджета: одна величина на двух языках.** Текст вопроса в
шаблоне обязан дословно совпадать с константой. Разойдись они — ревью по
шаблону и код (который однажды начнёт читать константу в свой гейт) требовали
бы РАЗНОГО, и «Security DoD пройден» означало бы разное в зависимости от того,
кто смотрит.

Заодно закреплён скелет самого шаблона: он появился в BIZ-60 срезе-1 как
носитель чек-листа приёмки экрана, но ничем не стерёгся — случайное удаление
секции прошло бы молча.
"""

from __future__ import annotations

import pathlib

import pytest

from app.core.product_spec import SECURITY_QUESTION, SIX_QUESTIONS

TEMPLATE = pathlib.Path(__file__).resolve().parents[1] / ".github" / "PULL_REQUEST_TEMPLATE.md"


@pytest.fixture(scope="module")
def template_text() -> str:
    assert TEMPLATE.exists(), "PR-шаблон удалён — чек-листы 60.x и Security DoD потеряны"
    return TEMPLATE.read_text(encoding="utf-8")


class TestСедьмойВопрос:
    def test_вопрос_в_шаблоне_дословно_из_константы(self, template_text: str) -> None:
        """Одна величина на двух языках (приём UX-бюджета).

        До этого среза константа не читалась никем — вопрос был записан и ни на
        что не влиял.
        """

        assert SECURITY_QUESTION in template_text

    def test_вопрос_обязателен_для_любого_pr(self, template_text: str) -> None:
        """Секция стоит ВЫШЕ экранного чек-листа и не ограничена «для экранов»:

        новую поверхность атаки вводит и ручка без экрана."""

        dod = template_text.index("Security DoD")
        screens = template_text.index("Чек-лист приёмки экрана")
        assert dod < screens
        assert "для любого PR" in template_text

    def test_пустой_ответ_не_разрешён_молчанием(self, template_text: str) -> None:
        """Шаблон требует явного «нет новых поверхностей», а не пропуска пункта:

        молчание и «проверено, поверхностей нет» — разные утверждения."""

        assert "нет\n      новых поверхностей" in template_text or (
            "нет новых поверхностей" in template_text.replace("\n      ", " ")
        )


class TestСкелетШаблона:
    """Шаблон появился в BIZ-60 срезе-1 и ничем не стерёгся."""

    @pytest.mark.parametrize(
        "section",
        [
            "## Что это",
            "## Сверка с ТЗ",
            "## Доказательства (local-evidence, канонический гейт)",
            "### 60.1 Ясность и фокус",
            "### 60.2 Прогрессивное раскрытие",
            "### 60.3 Понятность и подсказки",
            "### 60.4 Безопасность действий",
            "### 60.5 Единообразие и доступность",
            "### 60.6 Тест «нового пользователя»",
        ],
        ids=lambda s: s.strip("#").strip(),
    )
    def test_секция_на_месте(self, template_text: str, section: str) -> None:
        assert section in template_text, section


class TestКонстантыСпеки:
    def test_седьмой_вопрос_не_дублирует_шесть(self) -> None:
        """Вопрос называется седьмым, потому что шесть уже есть (разд. 21)."""

        assert SECURITY_QUESTION not in SIX_QUESTIONS
        assert len(SIX_QUESTIONS) == 6

    def test_вопрос_спрашивает_и_про_закрытие(self) -> None:
        """Половина вопроса — «как закрыты»: перечислить поверхности без
        ответа, что с ними сделано, значило бы составить меню для атакующего."""

        assert "как" in SECURITY_QUESTION and "закрыты" in SECURITY_QUESTION
