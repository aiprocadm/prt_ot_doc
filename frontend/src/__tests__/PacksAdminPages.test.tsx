import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

/**
 * Три служебных экрана комплектов: пресеты, профили и подробности прогона.
 * Все три read-only-реестры с одной формой, поэтому приёмка бюджета у них
 * общая — отдельные файлы дублировали бы одни и те же моки.
 */
const packsMock = vi.hoisted(() => ({
  getPresets: vi.fn(),
  getProfiles: vi.fn(),
  createPreset: vi.fn(),
  createProfile: vi.fn(),
  validatePreset: vi.fn(),
  getRunItems: vi.fn(),
  getRunTimeline: vi.fn(),
  retryFailedRunItems: vi.fn(),
}));

vi.mock("@/api/packs", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  packsApi: {
    getPresets: (...a: unknown[]) => packsMock.getPresets(...a),
    getProfiles: (...a: unknown[]) => packsMock.getProfiles(...a),
    createPreset: (...a: unknown[]) => packsMock.createPreset(...a),
    createProfile: (...a: unknown[]) => packsMock.createProfile(...a),
    validatePreset: (...a: unknown[]) => packsMock.validatePreset(...a),
    getRunItems: (...a: unknown[]) => packsMock.getRunItems(...a),
    getRunTimeline: (...a: unknown[]) => packsMock.getRunTimeline(...a),
    retryFailedRunItems: (...a: unknown[]) =>
      packsMock.retryFailedRunItems(...a),
  },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import PackagePresetsPage from "@/pages/packs/PackagePresetsPage";
import PackageProfilesPage from "@/pages/packs/PackageProfilesPage";
import PackRunDetailsPage from "@/pages/packs/PackRunDetailsPage";

const presets = [
  {
    id: "pr-1",
    code: "OT_BASE",
    name: "Базовый комплект ОТ",
    status: "active",
  },
  { id: "pr-2", code: "FIRE", name: "Пожарная безопасность", status: "draft" },
];
const profiles = [
  { id: "pf-1", code: "construction" },
  { id: "pf-2", code: "office" },
];
const runItems = [
  { id: "ri-1", row_no: 1, status: "done", file_name: "Приказ.docx" },
  {
    id: "ri-2",
    row_no: 2,
    status: "failed",
    file_name: "Журнал.docx",
    error_code: "MISSING_SOURCE_COLUMN",
  },
];

const renderAt = async (element: JSX.Element, path = "/") => {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path={path === "/" ? "/" : "/packs/runs/:id"}
            element={element}
          />
        </Routes>
      </MemoryRouter>,
    );
  });
};

describe("Служебные экраны комплектов", () => {
  beforeEach(() => {
    Object.values(packsMock).forEach((fn) => fn.mockReset());
    packsMock.getPresets.mockResolvedValue(presets);
    packsMock.getProfiles.mockResolvedValue(profiles);
    packsMock.getRunItems.mockResolvedValue(runItems);
    packsMock.getRunTimeline.mockResolvedValue([
      { id: "t-1", level: "info", message: "Прогон запущен" },
    ]);
  });

  it("пресеты: реестр наполнен и в UX-бюджете", async () => {
    await renderAt(<PackagePresetsPage />);

    expect(await screen.findByText(/Базовый комплект ОТ/)).toBeInTheDocument();
    const budget = uxBudgetDelta(document.body, "PackagePresetsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("профили: реестр наполнен и в UX-бюджете", async () => {
    await renderAt(<PackageProfilesPage />);

    expect(await screen.findByText(/construction/)).toBeInTheDocument();
    const budget = uxBudgetDelta(document.body, "PackageProfilesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("подробности прогона: строки видны с причиной отказа и в UX-бюджете", async () => {
    await renderAt(<PackRunDetailsPage />, "/packs/runs/run-1");

    expect(await screen.findByText(/Приказ.docx/)).toBeInTheDocument();
    // Отказ обязан называть причину: без неё строка «не получилось» бесполезна.
    expect(screen.getByText(/MISSING_SOURCE_COLUMN/)).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "PackRunDetailsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
