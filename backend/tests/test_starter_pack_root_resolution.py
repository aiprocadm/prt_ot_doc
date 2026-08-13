"""BIZ-52 срез-7: корень эталонов находится, а не угадывается счётом уровней.

Было `ROOT = Path(__file__).resolve().parents[6]` — промах мимо корня на один
уровень. Файл эталона не находился НИКОГДА: ни в обычной копии
(`/home/user/projects` вместо `/home/user/projects/prt_ot_doc`), ни в worktree
(там путь ещё длиннее). Выдача каждого арендатора молча писала
`starter_pack_missing`, и «главная техническая ценность для продажи» из
разд. 52.3 не работала вообще.

Этот тест — страж: он падает, если файл снова перестанет находиться, и его
сообщение объясняет, почему нельзя вернуться к счёту уровней.
"""

from __future__ import annotations

from app.services.tenants.bootstrap.service import STARTER_PACK_ROOT


def test_каталог_эталонов_существует() -> None:
    assert STARTER_PACK_ROOT.is_dir(), (
        f"каталог эталонов не найден: {STARTER_PACK_ROOT}. "
        "Корень репозитория ищется по ориентиру `seed/tenant_starter_packs`; "
        "счёт уровней вверх (`parents[N]`) ломается от переноса файла и от "
        "запуска из git worktree — так эта поломка и прожила незамеченной."
    )


def test_файл_эталона_по_умолчанию_на_месте() -> None:
    """Именно этот файл берёт выдача обычного (не демо) арендатора."""

    assert (STARTER_PACK_ROOT / "v1" / "default.json").is_file()


def test_демо_эталон_на_месте() -> None:
    assert (STARTER_PACK_ROOT / "v1" / "demo.json").is_file()
