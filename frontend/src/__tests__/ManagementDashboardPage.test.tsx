import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getExecutive: vi.fn(),
  getDashboard: vi.fn(),
  getTrend: vi.fn(),
  getBreakdown: vi.fn(),
  getCompanies: vi.fn(),
  getSites: vi.fn(),
  getContractors: vi.fn(),
}));

vi.mock("@/api/analyticsApi", () => ({ analyticsApi: api }));

import ManagementDashboardPage from "@/pages/analytics/ManagementDashboardPage";

const TREND = (metric: string) => ({
  metric,
  period: "daily" as const,
  series: [
    { date: "2026-07-01", value: 1 },
    { date: "2026-07-02", value: 3 },
  ],
});

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.getExecutive.mockResolvedValue({
    snapshot_date: "2026-07-11",
    widgets: {},
    dashboard: {
      name: "executive",
      widgets: {
        packages_total: 12,
        overdue_compliance_items: 3,
        open_incidents: 2,
        open_inspections: 1,
      },
    },
  });
  api.getDashboard.mockImplementation(async (name: string) =>
    name === "overdue"
      ? {
          name,
          widgets: {
            trainings_overdue: 4,
            ppe_overdue: 2,
            prescriptions_overdue: 1,
            plan_tasks_overdue: 0,
            overdue_compliance_items: 3,
          },
        }
      : {
          name,
          widgets: {
            workflow_open: 5,
            workflow_sla_breached: 1,
            plan_tasks_overdue: 0,
          },
        },
  );
  api.getTrend.mockImplementation(async (metric: string) => TREND(metric));
  api.getBreakdown.mockResolvedValue({
    dimension: "site",
    items: [
      {
        id: "s1",
        name: "Цех №1",
        incidents_open: 2,
        risks_high: 1,
        prescriptions_overdue: 0,
        total_issues: 3,
      },
      {
        id: "s2",
        name: "Офис",
        incidents_open: 0,
        risks_high: 0,
        prescriptions_overdue: 0,
        total_issues: 0,
      },
    ],
    total: 2,
  });
  api.getCompanies.mockResolvedValue({
    items: [{ id: "c1", name: "ООО Ромашка" }],
    total: 1,
  });
  api.getSites.mockResolvedValue({
    items: [{ id: "s1", name: "Цех №1" }],
    total: 1,
  });
  api.getContractors.mockResolvedValue({
    items: [{ id: "k1", name: "СтройПодряд" }],
    total: 1,
  });
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ManagementDashboardPage />
    </MemoryRouter>,
  );
}

describe("ManagementDashboardPage", () => {
  it("renders KPI cards from executive/overdue/sla-load", async () => {
    renderPage();
    expect(await screen.findByText("Открытые инциденты")).toBeInTheDocument();
    // "Просроченное обучение" is also a Trend chart title (TREND_METRICS) — collides as
    // a KPI-card query, so this assertion checks another overdue-sourced KPI instead
    // (ppe_overdue) to keep verifying the "overdue" dashboard widgets render.
    // Карточки overdue/sla-load приходят из ДРУГИХ моков и могут отрисоваться
    // позже executive — ждём каждую, иначе межэндпоинтная гонка.
    expect(await screen.findByText("Просроченные СИЗ")).toBeInTheDocument();
    expect(await screen.findByText("Нарушен SLA")).toBeInTheDocument();
  });

  it("renders six trend charts and switches period", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    expect(api.getTrend).toHaveBeenCalledTimes(6);
    await user.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() =>
      expect(api.getTrend).toHaveBeenCalledWith("incidents", "weekly"),
    );
  });

  it("passes filters to dashboard requests", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Компания"), "c1");
    await waitFor(() =>
      expect(api.getExecutive).toHaveBeenLastCalledWith(
        expect.objectContaining({ company_id: "c1" }),
      ),
    );
  });

  it("renders breakdown table and switches dimension", async () => {
    const user = userEvent.setup();
    renderPage();
    // "Цех №1" also appears as an <option> in the "Объект" select (getSites mock),
    // so the row lookup is scoped to the breakdown table to avoid an ambiguous match.
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Цех №1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "По подрядчикам" }));
    await waitFor(() =>
      expect(api.getBreakdown).toHaveBeenLastCalledWith(
        "contractor",
        expect.anything(),
      ),
    );
  });

  it("applies row click as a page filter (site drill-down)", async () => {
    const user = userEvent.setup();
    renderPage();
    const table = await screen.findByRole("table");
    const row = within(table).getByText("Цех №1");
    await user.click(row);
    await waitFor(() =>
      expect(api.getExecutive).toHaveBeenLastCalledWith(
        expect.objectContaining({ site_id: "s1" }),
      ),
    );
  });

  it("links to the profile sub-dashboards", async () => {
    renderPage();
    await screen.findByText("Открытые инциденты");
    const link = screen.getByRole("link", { name: /Executive/i });
    expect(link).toHaveAttribute("href", "/dashboard/executive");
  });

  it("does not apply a row filter for the site-less '— без объекта —' row (id empty)", async () => {
    api.getBreakdown.mockResolvedValue({
      dimension: "site",
      items: [
        {
          id: "",
          name: "— без объекта —",
          incidents_open: 1,
          risks_high: 0,
          prescriptions_overdue: 0,
          total_issues: 1,
        },
        {
          id: "s1",
          name: "Цех №1",
          incidents_open: 2,
          risks_high: 1,
          prescriptions_overdue: 0,
          total_issues: 3,
        },
      ],
      total: 2,
    });
    const user = userEvent.setup();
    renderPage();
    const row = await screen.findByText("— без объекта —");
    const callsBefore = api.getExecutive.mock.calls.length;
    await user.click(row);
    await waitFor(() =>
      expect(api.getExecutive.mock.calls.length).toBe(callsBefore),
    );
    expect(api.getExecutive).not.toHaveBeenLastCalledWith(
      expect.objectContaining({ site_id: "" }),
    );
  });

  it("hides the contractor filter when /contractors/registry is forbidden (403)", async () => {
    api.getContractors.mockRejectedValue(new Error("403"));
    renderPage();
    await screen.findByText("Открытые инциденты");
    expect(screen.queryByLabelText("Подрядчик")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Компания")).toBeInTheDocument();
    expect(screen.getByLabelText("Объект")).toBeInTheDocument();
  });
});
