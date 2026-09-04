import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  listDisciplineReports: vi.fn(),
  runDisciplineReport: vi.fn(),
}));

vi.mock("@/api/analyticsApi", () => ({ analyticsApi: api }));

import { DisciplineReportCard } from "@/components/analytics/DisciplineReportCard";
import type { DisciplineReportDto } from "@/types/dto/analytics";

const row = (
  discipline: string,
  title: string,
  incidents: number,
  overdue: number | null,
  delta: number | null,
) => ({
  discipline,
  title,
  incidents_open: incidents,
  overdue_items: overdue,
  total_issues: incidents + (overdue ?? 0),
  previous_total_issues:
    delta === null ? null : incidents + (overdue ?? 0) - delta,
  delta,
});

const latest: DisciplineReportDto = {
  id: "r2",
  period_start: "2026-08-28",
  period_end: "2026-09-04",
  total_issues: 7,
  summary:
    "Состояние на 04.09.2026: всего 7 (в отчёте за 28.08.2026 было 5, хуже на 2).",
  payload: {
    period: { start: "2026-08-28", end: "2026-09-04" },
    rows: [
      row("medical", "Медосмотры", 0, 3, 0),
      row("road_safety", "Безопасность дорожного движения", 2, null, 2),
      row("fire_safety", "Пожарная безопасность", 0, null, null),
    ],
    unmarked_incidents: 1,
    totals: {
      incidents_open: 3,
      overdue_items: 3,
      total_issues: 7,
      previous_total_issues: 5,
      delta: 2,
    },
    previous_period_end: "2026-08-28",
    worst: { discipline: "medical", title: "Медосмотры" },
    actions: ["Медосмотры: 3 просрочки"],
  },
};

const older: DisciplineReportDto = {
  ...latest,
  id: "r1",
  period_start: "2026-08-21",
  period_end: "2026-08-28",
  total_issues: 5,
  summary:
    "Состояние на 28.08.2026: всего 5 (первый отчёт — сравнивать не с чем).",
  payload: {
    ...latest.payload,
    previous_period_end: null,
    unmarked_incidents: 0,
  },
};

beforeEach(() => {
  api.listDisciplineReports.mockReset();
  api.runDisciplineReport.mockReset();
});

const renderCard = () =>
  render(
    <MemoryRouter>
      <DisciplineReportCard />
    </MemoryRouter>,
  );

describe("DisciplineReportCard (Доп. №1 разд. 57.4, срез-50)", () => {
  it("показывает свежий отчёт: итог словами, «—» где не считается, ссылка в реестр, динамика", async () => {
    api.listDisciplineReports.mockResolvedValue({
      items: [latest, older],
      total: 2,
    });
    renderCard();

    expect(await screen.findByText("Отчёт за 04.09.2026")).toBeInTheDocument();
    expect(screen.getByText("· сравнение с 28.08.2026")).toBeInTheDocument();
    expect(screen.getByTestId("discipline-report-summary")).toHaveTextContent(
      "хуже на 2",
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    // ДТП: число — ссылка в общий реестр с фильтром дисциплины; просрочки не считаются
    const road = rows[1];
    expect(within(road).getByRole("link", { name: "2" })).toHaveAttribute(
      "href",
      "/incidents?discipline=road_safety",
    );
    expect(
      within(road).getByTitle("По этой дисциплине не считается"),
    ).toHaveTextContent("—");
    expect(within(road).getByText("+2")).toBeInTheDocument();
    // без изменений — 0, а не пусто; нет прошлого — «—» с подсказкой
    expect(
      within(rows[0]).getByText("0", { selector: "td:last-child" }),
    ).toBeInTheDocument();
    expect(
      within(rows[2]).getByTitle("В прошлом отчёте сравнить не с чем"),
    ).toHaveTextContent("—");
    // неразмеченные — отдельной строкой со ссылкой в реестр
    expect(screen.getByText(/Не размечено дисциплиной/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "1" })).toHaveAttribute(
      "href",
      "/incidents",
    );
  });

  it("листает к прошлому отчёту и обратно без полей ввода", async () => {
    api.listDisciplineReports.mockResolvedValue({
      items: [latest, older],
      total: 2,
    });
    renderCard();
    await screen.findByText("Отчёт за 04.09.2026");

    await userEvent.click(screen.getByRole("button", { name: "← Раньше" }));
    expect(screen.getByText("Отчёт за 28.08.2026")).toBeInTheDocument();
    expect(screen.getByTestId("discipline-report-summary")).toHaveTextContent(
      "сравнивать не с чем",
    );
    expect(screen.queryByText(/сравнение с/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "← Раньше" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Позже →" }));
    expect(screen.getByText("Отчёт за 04.09.2026")).toBeInTheDocument();
  });

  it("«Собрать сейчас»: итог остаётся на экране, список перечитывается", async () => {
    api.listDisciplineReports
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({ items: [latest], total: 1 });
    api.runDisciplineReport.mockResolvedValue({
      created: true,
      report: latest,
      summary: "Отчёт собран",
    });
    renderCard();
    expect(await screen.findByText("Отчётов ещё нет")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Собрать сейчас" }),
    );

    expect(
      await screen.findByTestId("discipline-report-run-note"),
    ).toHaveTextContent("Отчёт собран");
    await waitFor(() =>
      expect(api.listDisciplineReports).toHaveBeenCalledTimes(2),
    );
    expect(await screen.findByText("Отчёт за 04.09.2026")).toBeInTheDocument();
    // кнопка сбора — вторичная: главных действий на дашборде и так два
    expect(
      screen.getByRole("button", { name: "Собрать сейчас" }),
    ).not.toHaveClass("bg-primary");
  });
});
