import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { OperationalDashboardDto } from "@/api/operationalDashboard";
import { CommandCenterPanel } from "@/components/operational/CommandCenterPanel";

const renderPanel = (props: Parameters<typeof CommandCenterPanel>[0]) =>
  render(
    <MemoryRouter>
      <CommandCenterPanel {...props} />
    </MemoryRouter>
  );

const data: OperationalDashboardDto = {
  tenant_id: "tenant-1",
  status: "critical",
  timestamp: "2026-06-15T00:00:00Z",
  health_status: "ok",
  alert_count: { critical: 1, high: 2 },
  alerts: [
    {
      id: "a1",
      category: "high_risk",
      severity: "critical",
      title: "Критический риск на объекте",
      description: "PxS высокий",
      count: 3,
      action_url: "/risk",
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-06-15T00:00:00Z",
      expires_at: null
    },
    {
      id: "a2",
      category: "overdue",
      severity: "high",
      title: "Просроченные обучения",
      description: null,
      count: 5,
      action_url: "/training",
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-06-15T00:00:00Z",
      expires_at: null
    },
    {
      id: "a3",
      category: "integration_error",
      severity: "high",
      title: "Сбой интеграции 1С",
      description: null,
      count: 1,
      action_url: null,
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-06-15T00:00:00Z",
      expires_at: null
    }
  ]
};

describe("CommandCenterPanel", () => {
  it("renders a card per non-empty category with RU labels and overall status", () => {
    renderPanel({ data });
    expect(screen.getByText("Высокий риск")).toBeInTheDocument();
    expect(screen.getByText("Просроченные")).toBeInTheDocument();
    expect(screen.getByText("Ошибки интеграций")).toBeInTheDocument();
    expect(screen.getByText("Критично")).toBeInTheDocument(); // overall status badge
  });

  it("sorts categories worst-severity first (critical category leads)", () => {
    renderPanel({ data });
    const cards = screen.getAllByTestId(/^cc-category-/);
    expect(cards[0]).toHaveAttribute("data-testid", "cc-category-high_risk");
  });

  it("shows severity summary chips from alert_count", () => {
    renderPanel({ data });
    const summary = screen.getByTestId("cc-severity-summary");
    expect(within(summary).getByText("Критичные: 1")).toBeInTheDocument();
    expect(within(summary).getByText("Высокие: 2")).toBeInTheDocument();
  });

  it("renders a 'Перейти' link only for internal action_url", () => {
    renderPanel({ data });
    const links = screen.getAllByRole("link", { name: /Перейти/ });
    expect(links).toHaveLength(2); // a1 (/risk) + a2 (/training); a3 has no url
  });

  it("renders empty state when there are no alerts", () => {
    renderPanel({ data: { ...data, status: "ok", alerts: [], alert_count: {} } });
    expect(screen.getByTestId("command-center-empty")).toHaveTextContent("Нет активных алертов");
  });

  it("renders error state and calls onRefresh", async () => {
    const onRefresh = vi.fn();
    renderPanel({ data: null, error: { message: "Network Error" }, onRefresh });
    expect(screen.getByTestId("command-center-error")).toHaveTextContent("Network Error");
    await userEvent.click(screen.getByRole("button", { name: /Обновить/ }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("renders a loading placeholder when there is no data yet", () => {
    renderPanel({ data: null, loading: true });
    expect(screen.getByText(/Загрузка командного центра/)).toBeInTheDocument();
  });

  it("renders committee_task alerts under the 'Задачи комитетов' label (срез-3)", () => {
    const withCommittee: OperationalDashboardDto = {
      ...data,
      alerts: [
        {
          id: "committee_tasks_overdue",
          category: "committee_task",
          severity: "high",
          title: "2 overdue committee task(s)",
          description: null,
          count: 2,
          action_url: "/committees",
          affected_entity_type: "committee_decision_task",
          affected_entity_id: null,
          created_at: "2026-06-15T00:00:00Z",
          expires_at: null
        }
      ]
    };
    renderPanel({ data: withCommittee });
    expect(screen.getByText("Задачи комитетов")).toBeInTheDocument();
    expect(screen.getByTestId("cc-category-committee_task")).toBeInTheDocument();
  });
});
