"""Сторож: экран не печатает служебное поле как есть (срез-180).

ЗАЧЕМ. Класс, который всплывал уже четырежды (срезы 150, 159, 160, 178): в
разметку попадает код из перечисления сервера — `draft`, `PENDING`,
`TrainingDueSoon`, — и человек читает латиницу вместо слова. Отдельно это
мелочь, вместе — ощущение, что программа говорит не на его языке.

Разбор ищет печать вида `{item.status}` в разметке. ВАЖНО: передача в
атрибут (`status={item.status}`) — НЕ печать: значение уходит в компонент,
который сам решает, как показать. Первый заход этого не учитывал и дал 101
ложное место из 101.

ПОЧЕМУ РЕЕСТР, А НЕ ЗАПРЕТ. Мест сразу нашлось 61 — это волна, а не срез.
Срез-180 починил семь (карточка шаблона, исходящая очередь, админский экран) и
завёл общие подписи `statusLabel`/`priorityLabel` для текстовых мест, где
компонент поставить нельзя. Остальное записано долгом: сторож держит, чтобы
число НЕ РОСЛО, а починенный экран обязан уйти из реестра.

КАК ЧИНИТЬ. В разметке — `<StatusBadge status={…} />`; в тексте, строке списка
или пункте выпадающего списка — `statusLabel(…)` / `priorityLabel(…)` из
`components/common/StatusBadge`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

#: Поля, значения которых почти всегда из закрытого списка.
FIELDS = (
    "status",
    "type",
    "kind",
    "priority",
    "severity",
    "channel",
    "state",
    "mode",
    "level",
    "result",
    "outcome",
    "direction",
)

_PRINT_RE = re.compile(
    r"\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\.(?:"
    + "|".join(FIELDS)
    + r"))\s*\}"
)
_ATTRIBUTE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\s*$")

#: Долг: экран -> сколько мест ещё печатают код. Число обязано УБЫВАТЬ.
#: Убрать строку, когда экран починен целиком.
RAW_PRINT_DEBT: dict[str, int] = {
    "frontend/src/components/common/LegalAcceptanceBanner.tsx": 1,
    "frontend/src/components/common/LegalLinks.tsx": 1,
    "frontend/src/components/JobTimeline.tsx": 1,
    "frontend/src/components/wizard/WizardJobTimeline.tsx": 1,
    "frontend/src/features/branches/BranchTable.tsx": 1,
    "frontend/src/features/companies/CompanyTable.tsx": 1,
    "frontend/src/features/documents/DocumentPreview.tsx": 2,
    "frontend/src/features/files/FileList.tsx": 1,
    "frontend/src/pages/admin/AdminPage.tsx": 1,
    "frontend/src/pages/admin/BillingPage.tsx": 1,
    "frontend/src/pages/approvals/ApprovalRoutesPage.tsx": 1,
    "frontend/src/pages/client-portal/ClientPortalDocumentsPage.tsx": 2,
    "frontend/src/pages/client-portal/ClientPortalHistoryPage.tsx": 1,
    "frontend/src/pages/client-portal/ClientPortalPackagesPage.tsx": 3,
    "frontend/src/pages/committees/CommitteesPage.tsx": 1,
    "frontend/src/pages/documents/DocumentsPage.tsx": 1,
    "frontend/src/pages/documents/QuickGeneratePage.tsx": 2,
    "frontend/src/pages/documents/wizard/steps/WizardStepSections.tsx": 2,
    "frontend/src/pages/edo/EdoPage.tsx": 1,
    "frontend/src/pages/findings/FindingsPage.tsx": 1,
    "frontend/src/pages/fire-training/FireTrainingPage.tsx": 3,
    "frontend/src/pages/managed-clients/ClientCockpitPage.tsx": 1,
    "frontend/src/pages/notifications/NotificationsPage.tsx": 2,
    "frontend/src/pages/packs/PackagePresetsPage.tsx": 1,
    "frontend/src/pages/packs/PackageProfilesPage.tsx": 1,
    "frontend/src/pages/packs/PackRunDetailsPage.tsx": 2,
    "frontend/src/pages/PipelineBuilderPage.tsx": 1,
    "frontend/src/pages/PipelineRunDetails.tsx": 1,
    "frontend/src/pages/PipelineRuns.tsx": 1,
    "frontend/src/pages/search/components/SearchResultsList.tsx": 1,
    "frontend/src/pages/signatures/SignaturesPage.tsx": 1,
    "frontend/src/pages/sout/SoutPage.tsx": 1,
    "frontend/src/pages/warehouse/WarehousePage.tsx": 3,
    "frontend/src/widgets/dashboard/DashboardTabsSection.tsx": 1,
    "frontend/src/widgets/dashboard/RecentObjectsSection.tsx": 1,
    "frontend/src/widgets/tasks/TaskFocusCard.tsx": 2,
    "frontend/src/widgets/workflow/WorkflowDefinitionsCard.tsx": 2,
    "frontend/src/widgets/workflow/WorkflowRuntimePanel.tsx": 3,
}


def _raw_prints() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for file in sorted(FRONTEND_SRC.rglob("*.tsx")):
        if ".test." in file.name or "__tests__" in file.parts:
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            for match in _PRINT_RE.finditer(line):
                if _ATTRIBUTE_RE.search(line[: match.start()]):
                    continue
                counts[str(file.relative_to(REPO_ROOT))] += 1
    return dict(counts)


def test_разбор_видит_разметку() -> None:
    counts = _raw_prints()
    assert counts, "разбор не нашёл ни одного места — он потерял область"
    assert (
        sum(counts.values()) < 200
    ), "мест подозрительно много: проверьте, не ловит ли разбор атрибуты"


def test_новых_экранов_с_печатью_кода_не_появилось() -> None:
    counts = _raw_prints()
    new_screens = sorted(set(counts) - set(RAW_PRINT_DEBT))
    assert not new_screens, (
        "на экране печатается служебное поле как есть — человек увидит код "
        "латиницей. В разметке используйте <StatusBadge>, в тексте — "
        "statusLabel()/priorityLabel():\n" + "\n".join(f"  {name}" for name in new_screens)
    )


def test_долг_не_растёт() -> None:
    counts = _raw_prints()
    grown = sorted(
        f"  {name}: было {RAW_PRINT_DEBT[name]}, стало {counts[name]}"
        for name in set(counts) & set(RAW_PRINT_DEBT)
        if counts[name] > RAW_PRINT_DEBT[name]
    )
    assert not grown, "мест с печатью кода стало больше:\n" + "\n".join(grown)


def test_реестр_не_протух() -> None:
    """Починили экран — уберите его из реестра, иначе долг числится вечно."""

    counts = _raw_prints()
    stale = sorted(name for name in RAW_PRINT_DEBT if name not in counts)
    assert not stale, "экран больше не печатает код — уберите его из реестра: " + ", ".join(stale)

    shrunk = sorted(
        f"  {name}: в реестре {RAW_PRINT_DEBT[name]}, осталось {counts[name]}"
        for name in set(counts) & set(RAW_PRINT_DEBT)
        if counts[name] < RAW_PRINT_DEBT[name]
    )
    assert not shrunk, (
        "мест стало меньше — обновите числа в реестре, чтобы долг не мог "
        "вернуться незаметно:\n" + "\n".join(shrunk)
    )
