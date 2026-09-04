import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SiteOverview } from "@/api/sites";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  overview: vi.fn(),
}));

vi.mock("@/api/sites", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  sitesApi: api,
}));

import SiteCardPage from "@/pages/sites/SiteCardPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

/**
 * Карточка площадки 360° (BIZ-54-57 срез-3, разд. 57.1).
 *
 * Проверяется то, ради чего экран сделан: все дисциплины ТЗ на ОДНОМ экране,
 * причина у каждой, факты не выдают активность за соответствие, а границы
 * («что не посчитано») названы, а не спрятаны.
 */

const OVERVIEW: SiteOverview = {
  site_id: "s1",
  name: "Цех №1",
  company_id: "c1",
  address: "ул. Заводская, 1",
  hazard_class: "II",
  is_hazardous_production_facility: true,
  opo_register_number: "А12-3456",
  overall: "red",
  disciplines: [
    {
      discipline: "medical",
      title: "Медосмотры",
      light: "red",
      reason: "Разрывы с эталоном — не оформлено вовсе: 1",
      required: 1,
      missing: 1,
      lapsed: 0,
      expiring: 0,
    },
    {
      discipline: "ppe",
      title: "СИЗ",
      light: "not_measured",
      reason: "Эталон не задан: у должностей клиента нет норм",
      required: 0,
      missing: 0,
      lapsed: 0,
      expiring: 0,
    },
    {
      discipline: "training",
      title: "Обучение",
      light: "not_measured",
      reason: "Эталон обучения не задан",
      required: 0,
      missing: 0,
      lapsed: 0,
      expiring: 0,
    },
    {
      discipline: "fire_safety",
      title: "Пожарная безопасность",
      light: "not_measured",
      reason:
        "Поимённый учёт пожарной безопасности в системе не ведётся. " +
        "К площадке привязано действующих нарядов-допусков: 2",
      required: 0,
      missing: 0,
      lapsed: 0,
      expiring: 0,
    },
    {
      discipline: "industrial_safety",
      title: "Промышленная безопасность",
      light: "not_measured",
      reason:
        "Поимённый учёт промышленной безопасности в системе не ведётся. " +
        "Площадка учтена как ОПО (А12-3456)",
      required: 0,
      missing: 0,
      lapsed: 0,
      expiring: 0,
    },
    {
      discipline: "ecology",
      title: "Экология",
      light: "not_measured",
      reason: "Поимённый учёт экологии в системе не ведётся",
      required: 0,
      missing: 0,
      lapsed: 0,
      expiring: 0,
    },
    {
      discipline: "civil_defense",
      title: "ГО и ЧС",
      light: "not_measured",
      reason: "Поимённый учёт ГО и ЧС в системе не ведётся",
      required: 0,
      missing: 0,
      lapsed: 0,
      expiring: 0,
    },
    {
      discipline: "road_safety",
      title: "БДД",
      light: "not_measured",
      reason: "Поимённый учёт БДД в системе не ведётся",
      required: 0,
      missing: 0,
      lapsed: 0,
      expiring: 0,
    },
  ],
  facts: {
    workplaces: 3,
    people: 12,
    people_without_workplace: 5,
    permits: {
      total: 3,
      by_discipline: { fire_safety: 2 },
      without_discipline: 1,
      without_discipline_titles: ["работа на высоте"],
      without_discipline_reason:
        "общая охрана труда: отдельной дисциплины для неё в словаре нет",
    },
  },
  not_counted: [
    { title: "Проверки", reason: "в системе три таблицы проверок" },
    { title: "Инциденты", reason: "в системе две таблицы инцидентов" },
    { title: "Риски", reason: "в системе три таблицы рисков" },
  ],
};

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/sites/s1"]}>
      <Routes>
        <Route path="/sites/:siteId" element={<SiteCardPage />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  api.overview.mockResolvedValue(OVERVIEW);
});

describe("SiteCardPage", () => {
  it("показывает ВСЕ дисциплины ТЗ на одном экране (приёмка §58.3)", async () => {
    renderPage();

    const table = await screen.findByTestId("disciplines");
    for (const title of [
      "Медосмотры",
      "СИЗ",
      "Обучение",
      "Пожарная безопасность",
      "Промышленная безопасность",
      "Экология",
      "ГО и ЧС",
      "БДД",
    ]) {
      expect(within(table).getByText(title)).toBeInTheDocument();
    }
  });

  it("у каждой дисциплины видна расшифровка, а не только цвет", async () => {
    renderPage();

    const table = await screen.findByTestId("disciplines");
    expect(
      within(table).getByText(/не оформлено вовсе: 1/),
    ).toBeInTheDocument();
    expect(within(table).getByText(/учтена как ОПО/)).toBeInTheDocument();
  });

  it("наряды-допуски видны фактом, но дисциплина остаётся «не измеряется»", async () => {
    renderPage();

    const table = await screen.findByTestId("disciplines");
    const fire = within(table).getByText("Пожарная безопасность").closest("tr");
    expect(fire).not.toBeNull();
    expect(
      within(fire as HTMLElement).getByText("Не измеряется"),
    ).toBeInTheDocument();
    expect(
      within(fire as HTMLElement).getByText(/нарядов-допусков: 2/),
    ).toBeInTheDocument();
  });

  it("люди без рабочего места названы числом, а не спрятаны", async () => {
    renderPage();

    const facts = await screen.findByTestId("people-without-workplace");
    expect(facts).toHaveTextContent("5");
  });

  it("виды работ без дисциплины названы словами", async () => {
    renderPage();

    const permits = await screen.findByTestId("site-permits");
    expect(permits).toHaveTextContent("работа на высоте");
    // И ПОЧЕМУ у них нет дисциплины: без причины число читается как недоделка.
    expect(permits).toHaveTextContent("общая охрана труда");
  });

  it("границы («что не посчитано») показаны с причиной", async () => {
    renderPage();

    const list = await screen.findByTestId("not-counted");
    expect(within(list).getByText(/Проверки/)).toBeInTheDocument();
    expect(within(list).getByText(/три таблицы рисков/)).toBeInTheDocument();
  });

  it("403 объяснён словами, а не выглядит поломкой", async () => {
    api.overview.mockRejectedValue({ status: 403, message: "Forbidden" });
    renderPage();

    expect(
      await screen.findByText("Доступ только у администратора"),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    renderPage();
    await screen.findByTestId("disciplines");

    const budget = uxBudgetDelta(document.body, "SiteCardPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("измеритель бюджета ВИДИТ блоки этого экрана", async () => {
    // Сторож против пустой проверки: если блоки не помечены `data-ux-block`,
    // измеритель насчитает ноль и «бюджет соблюдён» будет означать «нечего
    // мерить» — проверка хуже отсутствующей.
    renderPage();
    await screen.findByTestId("disciplines");

    const { countDashboardBlocks } = await import("@/test-utils/uxBudget");
    expect(countDashboardBlocks(document.body)).toBe(3);
  });

  it("до списка площадок можно вернуться", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("← К списку площадок")).toBeInTheDocument(),
    );
  });
});
