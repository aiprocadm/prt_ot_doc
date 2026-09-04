import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AttentionPanel } from "@/components/common/AttentionPanel";

const getAttentionMock = vi.fn();

vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    getAttention: (...args: unknown[]) => getAttentionMock(...args),
  },
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
        readiness_blockers: 2,
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
          action_hint: "Откройте реестр сотрудников и назначьте медосмотр",
        },
      ],
      recommendations: ["Закрыть просроченные задачи по обучению"],
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>,
    );

    // Ждём сами данные из getAttention: заголовок «Центр внимания» статичен
    // и появляется ДО ответа API — синхронные getBy* давали гонку.
    expect(await screen.findByText("2 просроченных задач")).toBeInTheDocument();
    expect(screen.getByText("Центр внимания")).toBeInTheDocument();
    expect(screen.getByText("Сотрудники без медосмотра")).toBeInTheDocument();
    expect(
      screen.getByText("Закрыть просроченные задачи по обучению"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Открыть рабочий экран" }),
    ).toHaveAttribute("href", "/persons");
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
        readiness_blockers: 1,
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
          action_hint: "Заполните контакты",
        },
      ],
      recommendations: [],
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Неполные контакты сотрудников"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Открыть реестр сотрудников" }),
    ).toHaveAttribute("href", "/persons");
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
        readiness_blockers: 1,
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
          action_hint:
            "Закройте просроченные назначения или перепланируйте сроки",
        },
      ],
      recommendations: [],
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Просроченные обучения"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Открыть задачи по обучению" }),
    ).toHaveAttribute("href", "/tasks?type=training_plan&overdue=true");
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
        readiness_blockers: 0,
      },
      items: [],
      blockers: [],
      recommendations: [],
    });

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Нет критичных нарушений"),
    ).toBeInTheDocument();
  });

  // ── BIZ-54-57 срез-1: дисциплины и записи внимания (разд. 57.2) ──────────

  const withDisciplines = () => ({
    generated_at: "2026-08-18T00:00:00Z",
    summary: {
      overdue_tasks: 0,
      due_soon_tasks: 0,
      overdue_deadlines: 0,
      pending_sync_batches: 0,
      failed_sync_batches: 0,
      readiness_blockers: 0,
    },
    items: [
      {
        item_type: "medical_exam",
        id: "medical_exam:e1",
        severity: "critical",
        title: "Медосмотр: Иванов И.И.",
        status: "overdue",
        due_at: "2026-07-01T00:00:00Z",
        entity_type: "medical_exam",
        entity_id: "e1",
        reason: "Срок прошёл",
        discipline: "medical",
      },
      {
        item_type: "task",
        id: "t1",
        severity: "critical",
        title: "Просроченная задача",
        status: "open",
        due_at: "2026-07-02T00:00:00Z",
        entity_type: null,
        entity_id: null,
        reason: "Задача просрочена",
        discipline: null,
      },
    ],
    blockers: [],
    recommendations: [],
    disciplines: [
      {
        code: "medical",
        title: "Медосмотры",
        measured: true,
        overdue: 1,
        due_soon: 0,
        reason: null,
      },
      {
        code: "ecology",
        title: "Экология",
        measured: false,
        overdue: 0,
        due_soon: 0,
        reason: "Поимённый учёт экологии в системе не ведётся",
      },
    ],
    unclassified_sources: [
      "Наряд-допуск: вид работ хранится свободной строкой",
    ],
  });

  it("рисует записи внимания — раньше сервер считал список, который выбрасывался", async () => {
    getAttentionMock.mockResolvedValueOnce(withDisciplines());

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Медосмотр: Иванов И.И."),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("attention-item")).toHaveLength(2);
    // Запись дисциплины подписана; задача без дисциплины бейджа не получает.
    expect(screen.getByText("Медосмотры")).toBeInTheDocument();
  });

  it("неизмеряемая дисциплина говорит «учёт не ведётся», а не показывает ноль", async () => {
    getAttentionMock.mockResolvedValueOnce(withDisciplines());

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>,
    );

    await screen.findByTestId("attention-disciplines");
    const chips = screen.getAllByTestId("attention-discipline");
    const ecology = chips.find((chip) =>
      chip.textContent?.includes("Экология"),
    );
    expect(ecology).toBeDefined();
    expect(ecology).toHaveTextContent("учёт не ведётся");
    expect(ecology).not.toHaveTextContent("нарушений нет");
    // Причина доступна как подсказка, а не спрятана.
    expect(ecology).toHaveAttribute(
      "title",
      "Поимённый учёт экологии в системе не ведётся",
    );
  });

  it("старый ответ без дисциплин не ломает панель", async () => {
    const legacy = withDisciplines();
    delete (legacy as { disciplines?: unknown }).disciplines;
    delete (legacy as { unclassified_sources?: unknown }).unclassified_sources;
    getAttentionMock.mockResolvedValueOnce(legacy);

    render(
      <MemoryRouter>
        <AttentionPanel />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Медосмотр: Иванов И.И."),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("attention-disciplines"),
    ).not.toBeInTheDocument();
  });
});
