import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AttentionPanel } from "@/components/common/AttentionPanel";

const getAttentionMock = vi.fn();

vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    getAttention: (...args: unknown[]) => getAttentionMock(...args)
  }
}));

describe("AttentionPanel", () => {
  it("renders summary, blockers and recommendations", async () => {
    getAttentionMock.mockResolvedValueOnce({
      generated_at: "2026-03-23T00:00:00Z",
      summary: {
        overdue_tasks: 2,
        due_soon_tasks: 1,
        overdue_deadlines: 1,
        pending_sync_batches: 3,
        failed_sync_batches: 1,
        readiness_blockers: 2
      },
      items: [],
      blockers: [
        {
          code: "employees_missing_medical",
          title: "Сотрудники без медосмотра",
          severity: "critical",
          count: 4,
          reason: "Есть сотрудники с истекшим или отсутствующим медосмотром",
          entity_type: "person",
          action_hint: "Откройте реестр сотрудников и назначьте медосмотр"
        }
      ],
      recommendations: ["Закрыть просроченные задачи по обучению"]
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>
    );

    expect(await screen.findByText("Центр внимания")).toBeInTheDocument();
    expect(screen.getByText("2 просроченных задач")).toBeInTheDocument();
    expect(screen.getByText("Сотрудники без медосмотра")).toBeInTheDocument();
    expect(screen.getByText("Закрыть просроченные задачи по обучению")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть рабочий экран" })).toHaveAttribute("href", "/persons");
  });

  it("uses explicit CTA for employees_missing_contacts → /persons", async () => {
    getAttentionMock.mockResolvedValueOnce({
      generated_at: "2026-03-23T00:00:00Z",
      summary: {
        overdue_tasks: 0,
        due_soon_tasks: 0,
        overdue_deadlines: 0,
        pending_sync_batches: 0,
        failed_sync_batches: 0,
        readiness_blockers: 1
      },
      items: [],
      blockers: [
        {
          code: "employees_missing_contacts",
          title: "Неполные контакты сотрудников",
          severity: "high",
          count: 3,
          reason: "Нужен email или телефон",
          entity_type: "person",
          action_hint: "Заполните контакты"
        }
      ],
      recommendations: []
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>
    );

    expect(await screen.findByText("Неполные контакты сотрудников")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть реестр сотрудников" })).toHaveAttribute("href", "/persons");
  });

  it("maps blocker code to scenario-aware action screen", async () => {
    getAttentionMock.mockResolvedValueOnce({
      generated_at: "2026-03-23T00:00:00Z",
      summary: {
        overdue_tasks: 0,
        due_soon_tasks: 0,
        overdue_deadlines: 0,
        pending_sync_batches: 0,
        failed_sync_batches: 0,
        readiness_blockers: 1
      },
      items: [],
      blockers: [
        {
          code: "training_overdue",
          title: "Просроченные обучения",
          severity: "high",
          count: 2,
          reason: "Просроченные назначения обучения",
          entity_type: "training_enrollment",
          action_hint: "Закройте просроченные назначения или перепланируйте сроки"
        }
      ],
      recommendations: []
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>
    );

    expect(await screen.findByText("Просроченные обучения")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть задачи по обучению" })).toHaveAttribute(
      "href",
      "/tasks?type=training_plan&overdue=true"
    );
  });

  it("renders all-clear state", async () => {
    getAttentionMock.mockResolvedValueOnce({
      generated_at: "2026-03-23T00:00:00Z",
      summary: {
        overdue_tasks: 0,
        due_soon_tasks: 0,
        overdue_deadlines: 0,
        pending_sync_batches: 0,
        failed_sync_batches: 0,
        readiness_blockers: 0
      },
      items: [],
      blockers: [],
      recommendations: []
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>
    );

    expect(await screen.findByText("Нет критичных нарушений")).toBeInTheDocument();
  });
});
