import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const operationsApiMock = vi.hoisted(() => ({
  getReferenceSnapshot: vi.fn(),
}));

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getReferenceSnapshot: (...args: unknown[]) =>
      operationsApiMock.getReferenceSnapshot(...args),
  },
}));

import ReferencePage from "@/pages/reference/ReferencePage";

// Наполненный снимок справочников: длины НАРОЧНО разные, чтобы каждая цифра
// на экране однозначно указывала на свой справочник.
const filledSnapshot = {
  npa: [
    { id: "npa-1", code: "N-1", title: "Приказ 1" },
    { id: "npa-2", code: "N-2", title: "Приказ 2" },
    { id: "npa-3", code: "N-3", title: "Приказ 3" },
  ],
  ppeItems: [
    { id: "ppe-1", name: "Каска" },
    { id: "ppe-2", name: "Перчатки" },
  ],
  programs: [
    { id: "prog-1", title: "Программа A" },
    { id: "prog-2", title: "Программа B" },
    { id: "prog-3", title: "Программа C" },
    { id: "prog-4", title: "Программа D" },
  ],
  templates: [
    { id: "tpl-1", name: "Шаблон 1" },
    { id: "tpl-2", name: "Шаблон 2" },
    { id: "tpl-3", name: "Шаблон 3" },
    { id: "tpl-4", name: "Шаблон 4" },
    { id: "tpl-5", name: "Шаблон 5" },
  ],
  briefingTemplates: [{ id: "brief-1", name: "Вводный" }],
};

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <ReferencePage />
      </MemoryRouter>,
    );
  });
  // Ждём данные: «5» — счётчик шаблонов документов, он появляется только
  // после ответа мока (initialData — пустые списки).
  expect(await screen.findByText("5")).toBeInTheDocument();
};

describe("ReferencePage", () => {
  beforeEach(() => {
    operationsApiMock.getReferenceSnapshot.mockReset();
    operationsApiMock.getReferenceSnapshot.mockResolvedValue(filledSnapshot);
  });

  it("показывает наполнение справочников по карточкам", async () => {
    await renderPage();

    expect(screen.getByText("НПА")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("СИЗ")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Программы обучения")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Шаблоны инструктажей")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    // Площадки — карточка без счётчика (доступ читает только администратор).
    expect(screen.getByText("Площадки")).toBeInTheDocument();
    expect(
      screen.queryByText("Справочники пока пусты"),
    ).not.toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных (BIZ-60 волна 5)", async () => {
    await renderPage();

    const budget = uxBudgetDelta(document.body, "ReferencePage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
