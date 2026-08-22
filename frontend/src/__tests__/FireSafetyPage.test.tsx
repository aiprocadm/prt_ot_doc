import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FireSafetyPage from "@/pages/fire-safety/FireSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getFireSafetySnapshotMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getFireSafetySnapshot: (...args: unknown[]) =>
      getFireSafetySnapshotMock(...args),
  },
}));

/** Наполненный снимок: статистика шапки и реестр площадок на экране. */
const populatedFireSafetySnapshot = {
  sites: [
    {
      id: "site-1",
      company_id: "comp-1",
      name: "Цех сборки №1",
      address: "г. Тверь, ул. Заводская, 5",
      hazard_class: "В2",
      contact_name: "Иванов И. И.",
    },
    {
      id: "site-2",
      company_id: "comp-1",
      name: "Склад ГСМ",
      address: null,
      hazard_class: null,
      contact_name: null,
    },
  ],
  inspections: [
    { id: "insp-1", site_id: "site-1", status: "scheduled" },
    { id: "insp-2", site_id: "site-1", status: "done" },
  ],
  tasks: [
    { id: "task-1", status: "open" },
    { id: "task-2", status: "done" },
  ],
};

describe("FireSafetyPage", () => {
  beforeEach(() => {
    getFireSafetySnapshotMock.mockReset();
  });

  it("рисует реестр объектов защиты по данным снимка", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    expect(
      screen.getByText(/пожарная безопасность · объекты защиты/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Склад ГСМ")).toBeInTheDocument();
    // Связанные проверки посчитаны по site_id: у первой площадки их две.
    expect(screen.getByText("2 шт.")).toBeInTheDocument();
    expect(screen.getByText("Иванов И. И.")).toBeInTheDocument();
  });

  // Приёмка UX-бюджета (ТЗ разд. 59.2, BIZ-60): меряем ОТРИСОВАННЫЙ
  // наполненный экран — статистика шапки и таблица реестра видны.

  it("FireSafetyPage в UX-бюджете", async () => {
    getFireSafetySnapshotMock.mockResolvedValue(populatedFireSafetySnapshot);

    render(
      <MemoryRouter>
        <FireSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Цех сборки №1")).toBeInTheDocument();
    expect(screen.getByText(/реестр объектов защиты/i)).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "FireSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
