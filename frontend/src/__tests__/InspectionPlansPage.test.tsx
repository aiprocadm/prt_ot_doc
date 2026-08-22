import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const operationsApiMock = vi.hoisted(() => ({
  getInspectionWorkspaceSnapshot: vi.fn(),
}));

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getInspectionWorkspaceSnapshot: (...args: unknown[]) =>
      operationsApiMock.getInspectionWorkspaceSnapshot(...args),
  },
}));

import InspectionPlansPage from "@/pages/inspection-plans/InspectionPlansPage";

/**
 * Наполненный снапшот: даты фиксированы далеко в прошлом/будущем, чтобы тест
 * не зависел от текущего дня (просрочка считается через Date.now()).
 * insp-2 просрочена и не закрыта, task-1 открыта — вместе они включают
 * карточку «Блокеры и дальнейшие действия», то есть меряем САМОЕ полное
 * состояние экрана: шапка + карточка блокеров + таблица реестра.
 */
const snapshot = {
  inspections: [
    {
      id: "insp-1",
      authority: "Ростехнадзор",
      purpose: "Плановая проверка охраны труда",
      scheduled_at: "2099-05-12T10:00:00Z",
      status: "planned",
    },
    {
      id: "insp-2",
      authority: "ГИТ",
      purpose: "Внеплановая проверка",
      scheduled_at: "2020-01-15T10:00:00Z",
      status: "in_progress",
    },
    {
      id: "insp-3",
      authority: "Роспотребнадзор",
      purpose: null,
      scheduled_at: null,
      status: "done",
    },
  ],
  prescriptions: [
    {
      id: "presc-1",
      inspection_id: "insp-2",
      description: "Устранить нарушение",
      status: "open",
    },
  ],
  tasks: [
    { id: "task-1", title: "Подготовить документы", status: "open" },
    { id: "task-2", title: "Закрытая задача", status: "done" },
  ],
  templates: [{ id: "tpl-1", name: "Шаблон акта проверки" }],
  packRuns: [{ id: "pack-1" }],
};

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <InspectionPlansPage />
      </MemoryRouter>,
    );
  });
};

describe("InspectionPlansPage", () => {
  beforeEach(() => {
    operationsApiMock.getInspectionWorkspaceSnapshot.mockReset();
    operationsApiMock.getInspectionWorkspaceSnapshot.mockResolvedValue(
      snapshot,
    );
  });

  it("рисует реестр планов и карточку блокеров по данным снапшота", async () => {
    await renderPage();

    expect(await screen.findByText("Ростехнадзор")).toBeInTheDocument();
    expect(screen.getByText("ГИТ")).toBeInTheDocument();
    expect(screen.getByText("Роспотребнадзор")).toBeInTheDocument();
    expect(
      screen.getByText("Плановая проверка охраны труда"),
    ).toBeInTheDocument();

    // insp-2 просрочена (2020 год, не закрыта) + task-1 открыта → карточка.
    expect(
      screen.getByText(/Просроченных плановых проверок: 1/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Открытых задач по планам: 1/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Открыть задачи" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Открыть реестр проверок" }),
    ).toBeInTheDocument();
    expect(
      operationsApiMock.getInspectionWorkspaceSnapshot,
    ).toHaveBeenCalledTimes(1);
  });

  it("наполненный экран в UX-бюджете (BIZ-60 волна 5)", async () => {
    await renderPage();

    expect(await screen.findByText("Ростехнадзор")).toBeInTheDocument();
    // Карточка блокеров тоже видна — меряем экран в самом полном состоянии.
    expect(
      screen.getByText(/Просроченных плановых проверок: 1/),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "InspectionPlansPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
