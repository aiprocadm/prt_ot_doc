import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/i18n";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const reportsApiMock = vi.hoisted(() => ({
  getExports: vi.fn(),
  getExportSchedules: vi.fn(),
  getExportKpis: vi.fn(),
  getDatasets: vi.fn(),
}));

vi.mock("@/api/reports", () => ({
  reportsApi: {
    getExports: (...args: unknown[]) => reportsApiMock.getExports(...args),
    getExportSchedules: (...args: unknown[]) =>
      reportsApiMock.getExportSchedules(...args),
    getExportKpis: (...args: unknown[]) =>
      reportsApiMock.getExportKpis(...args),
    getDatasets: (...args: unknown[]) => reportsApiMock.getDatasets(...args),
  },
}));

import ExportsPage from "@/pages/exports/ExportsPage";

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <ExportsPage />
      </MemoryRouter>,
    );
  });
};

describe("ExportsPage", () => {
  beforeEach(() => {
    Object.values(reportsApiMock).forEach((mock) => mock.mockReset());

    reportsApiMock.getExports.mockResolvedValue({
      total: 3,
      items: [
        {
          id: "job-1",
          dataset_code: "incidents_v1",
          schema_version: "v2",
          anonymized: true,
          target_type: "s3",
        },
        {
          id: "job-2",
          dataset_code: "training_v1",
          schema_version: "v1",
          anonymized: false,
          target_type: "file",
        },
        { id: "job-3" },
      ],
    });
    reportsApiMock.getExportSchedules.mockResolvedValue({ total: 4 });
    reportsApiMock.getExportKpis.mockResolvedValue({ total: 7 });
    reportsApiMock.getDatasets.mockResolvedValue({
      total: 2,
      items: [
        { code: "incidents_v1", schema_version: "v2", targets: ["file", "s3"] },
        { code: "training_v1", schema_version: "v1", targets: ["file"] },
      ],
    });
  });

  it("renders counters, job preview and dataset catalog from API", async () => {
    await renderPage();

    // Наполненный экран: код набора виден и в превью заданий, и в каталоге
    // наборов — поэтому ждём ИМЕННО два вхождения, а не одно.
    expect(await screen.findAllByText("incidents_v1")).toHaveLength(2);
    expect(await screen.findAllByText("training_v1")).toHaveLength(2);
    // У задания без dataset_code показывается его id.
    expect(await screen.findByText("job-3")).toBeInTheDocument();
    // Счётчики трёх карточек: задания / расписания / KPI.
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(reportsApiMock.getExports).toHaveBeenCalled();
    expect(reportsApiMock.getDatasets).toHaveBeenCalled();
  });

  it("экран в UX-бюджете на наполненных данных (BIZ-60)", async () => {
    await renderPage();

    // Меряем ЗАПОЛНЕННЫЙ экран: и превью заданий, и каталог наборов на месте
    // (по два вхождения кода набора) — иначе замер прошёл бы на пустом
    // состоянии и ничего не доказал.
    expect(await screen.findAllByText("incidents_v1")).toHaveLength(2);
    expect(await screen.findAllByText("training_v1")).toHaveLength(2);
    expect(await screen.findByText("job-3")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "ExportsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
