import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SitePage } from "@/api/sites";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  overview: vi.fn(),
}));

vi.mock("@/api/sites", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  sitesApi: api,
}));

import SitesPage from "@/pages/sites/SitesPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

/**
 * Реестр площадок (BIZ-54-57 срез-3): вход в карточку 360°.
 *
 * Главное здесь — ссылка на карточку. Экрана площадок в интерфейсе не было
 * вовсе, и карточка без входа была бы страницей, до которой нельзя дойти.
 */

const PAGE: SitePage = {
  total: 2,
  items: [
    {
      id: "s1",
      company_id: "c1",
      name: "Цех №1",
      address: "ул. Заводская, 1",
      hazard_class: "II",
      is_hazardous_production_facility: true,
      opo_register_number: "А12-3456",
    },
    {
      id: "s2",
      company_id: "c1",
      name: "Склад",
      address: null,
      hazard_class: null,
      is_hazardous_production_facility: false,
      opo_register_number: null,
    },
  ],
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <SitesPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue(PAGE);
});

describe("SitesPage", () => {
  it("имя площадки ведёт в карточку 360°", async () => {
    renderPage();

    const link = await screen.findByRole("link", { name: "Цех №1" });
    expect(link).toHaveAttribute("href", "/sites/s1");
  });

  it("признак ОПО виден в списке, а не только в карточке", async () => {
    renderPage();

    const table = await screen.findByRole("table");
    expect(within(table).getByText("А12-3456")).toBeInTheDocument();
  });

  it("пустые поля показаны прочерком, а не пустотой", async () => {
    renderPage();

    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    renderPage();
    await screen.findByRole("table");

    const budget = uxBudgetDelta(document.body, "SitesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("измеритель бюджета ВИДИТ таблицу этого экрана", async () => {
    // Сторож против пустой проверки: без таблицы измеритель вернул бы ноль
    // колонок, и «бюджет соблюдён» означало бы «нечего мерить».
    renderPage();
    await screen.findByRole("table");

    const { countTableColumns } = await import("@/test-utils/uxBudget");
    expect(countTableColumns(document.body)).toBe(4);
  });
});
