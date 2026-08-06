import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { rulesApi } from "@/api/rules";
import type {
  AutomationRuleRead,
  EventTypeMeta,
  TriggerRead,
} from "@/types/dto/rules";

import RulesPage from "./RulesPage";

vi.mock("@/api/rules", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/rules")>();
  return {
    ...actual,
    rulesApi: {
      eventTypes: vi.fn(),
      list: vi.fn(),
      create: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      dryRun: vi.fn(),
      test: vi.fn(),
      triggers: vi.fn(),
    },
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function"
      ? (children as (allowed: boolean) => unknown)(true)
      : children,
}));

const EVENT_TYPES: EventTypeMeta[] = [
  {
    event_type: "IncidentCreated",
    fields: [
      { name: "severity", kind: "string" },
      { name: "injury_count", kind: "number" },
    ],
  },
  {
    event_type: "TaskOverdue",
    fields: [
      { name: "task_id", kind: "string" },
      { name: "overdue", kind: "boolean" },
    ],
  },
];

const RULE: AutomationRuleRead = {
  id: "r1",
  name: "Критичные инциденты",
  description: null,
  event_type: "IncidentCreated",
  conditions_json: {
    match: "all",
    conditions: [{ field: "severity", op: "eq", value: "critical" }],
  },
  actions_json: [
    {
      type: "notify",
      recipient_mode: "role",
      roles: ["admin"],
      title_template: "Инцидент",
      body_template: "Критичный инцидент",
    },
  ],
  priority: 100,
  is_enabled: true,
  created_at: "2026-07-10T00:00:00Z",
  updated_at: "2026-07-10T00:00:00Z",
};

const TRIGGER: TriggerRead = {
  id: "t1",
  rule_id: "r1",
  event_type: "IncidentCreated",
  event_key: "incident:1",
  correlation_id: null,
  status: "success",
  actions_result: [{ type: "notify", outcome: "created" }],
  created_at: "2026-07-10T10:00:00Z",
};

const FEATURE_OFF_ERROR = {
  status: 404,
  message: "Rules engine feature is not enabled for this tenant",
};

beforeEach(() => {
  vi.clearAllMocks();
  (rulesApi.list as any).mockResolvedValue({
    items: [RULE],
    total: 1,
    limit: 100,
    offset: 0,
  });
  (rulesApi.eventTypes as any).mockResolvedValue({
    items: EVENT_TYPES,
    total: EVENT_TYPES.length,
  });
  (rulesApi.triggers as any).mockResolvedValue({
    items: [TRIGGER],
    total: 1,
    limit: 50,
    offset: 0,
  });
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <RulesPage />
    </MemoryRouter>,
  );

describe("RulesPage", () => {
  it("renders the rules registry with RU event labels and action badges", async () => {
    renderPage();
    expect(
      (await screen.findAllByText("Критичные инциденты")).length,
    ).toBeGreaterThan(0);
    // Метка события: в таблице правил и в журнале срабатываний.
    expect(screen.getAllByText("Создан инцидент").length).toBeGreaterThan(0);
    // Бейдж действия в таблице (в журнале — «Уведомление: создано», не совпадает по полной строке).
    expect(screen.getByText("Уведомление")).toBeInTheDocument();
    expect(screen.getByText("1 условие")).toBeInTheDocument();
  });

  it("shows the feature-off empty state when the API answers feature-disabled 404", async () => {
    (rulesApi.list as any).mockRejectedValue(FEATURE_OFF_ERROR);
    (rulesApi.eventTypes as any).mockRejectedValue(FEATURE_OFF_ERROR);
    (rulesApi.triggers as any).mockRejectedValue(FEATURE_OFF_ERROR);
    renderPage();
    expect(await screen.findByText("Функция недоступна")).toBeInTheDocument();
  });

  it("creates a rule through the form dialog", async () => {
    (rulesApi.create as any).mockResolvedValue({
      ...RULE,
      id: "r2",
      name: "Тестовое правило",
    });
    renderPage();
    await screen.findAllByText("Критичные инциденты");

    fireEvent.click(screen.getByRole("button", { name: "Новое правило" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Имя"), {
      target: { value: "Тестовое правило" },
    });
    fireEvent.change(within(dialog).getByLabelText("Событие"), {
      target: { value: "IncidentCreated" },
    });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Добавить условие" }),
    );
    const conditionRow = within(dialog).getByTestId("cond-row-0");
    fireEvent.change(within(conditionRow).getByLabelText("Поле"), {
      target: { value: "severity" },
    });
    fireEvent.change(within(conditionRow).getByLabelText("Оператор"), {
      target: { value: "eq" },
    });
    fireEvent.change(within(conditionRow).getByLabelText("Значение"), {
      target: { value: "critical" },
    });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Добавить действие" }),
    );
    const actionCard = within(dialog).getByTestId("action-card-0");
    fireEvent.change(within(actionCard).getByLabelText("Тип действия"), {
      target: { value: "notify" },
    });
    fireEvent.change(within(actionCard).getByLabelText("Получатель"), {
      target: { value: "role" },
    });
    fireEvent.click(within(actionCard).getByLabelText("Администратор"));
    fireEvent.change(
      within(actionCard).getByLabelText("Заголовок уведомления"),
      { target: { value: "Заголовок" } },
    );
    fireEvent.change(within(actionCard).getByLabelText("Текст уведомления"), {
      target: { value: "Текст" },
    });

    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(rulesApi.create).toHaveBeenCalled());
    const [payload] = (rulesApi.create as any).mock.calls[0];
    expect(payload).toMatchObject({
      name: "Тестовое правило",
      event_type: "IncidentCreated",
      conditions_json: {
        match: "all",
        conditions: [{ field: "severity", op: "eq", value: "critical" }],
      },
    });
    expect(payload.actions_json[0]).toMatchObject({
      type: "notify",
      recipient_mode: "role",
      roles: ["admin"],
      title_template: "Заголовок",
      body_template: "Текст",
    });
  });

  it("submits boolean-field condition values as real booleans, not strings", async () => {
    (rulesApi.create as any).mockResolvedValue({
      ...RULE,
      id: "r3",
      name: "Булево правило",
    });
    renderPage();
    await screen.findAllByText("Критичные инциденты");

    fireEvent.click(screen.getByRole("button", { name: "Новое правило" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Имя"), {
      target: { value: "Булево правило" },
    });
    fireEvent.change(within(dialog).getByLabelText("Событие"), {
      target: { value: "TaskOverdue" },
    });

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Добавить условие" }),
    );
    const conditionRow = within(dialog).getByTestId("cond-row-0");
    // Переключение на boolean-поле: значение сидится "true", виджет — селект да/нет.
    fireEvent.change(within(conditionRow).getByLabelText("Поле"), {
      target: { value: "overdue" },
    });
    expect(within(conditionRow).getByLabelText("Значение")).toHaveValue("true");

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Добавить действие" }),
    );
    const actionCard = within(dialog).getByTestId("action-card-0");
    fireEvent.change(within(actionCard).getByLabelText("Тип действия"), {
      target: { value: "webhook" },
    });

    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(rulesApi.create).toHaveBeenCalled());
    const [payload] = (rulesApi.create as any).mock.calls[0];
    // Строгая проверка: настоящий boolean true, не строка "true".
    expect(payload.conditions_json.conditions[0]).toEqual({
      field: "overdue",
      op: "eq",
      value: true,
    });
    expect(payload.actions_json).toEqual([{ type: "webhook" }]);
  });

  it("runs a dry-run and shows the matched badge", async () => {
    (rulesApi.dryRun as any).mockResolvedValue({
      matched: true,
      condition_results: [
        {
          field: "severity",
          op: "eq",
          value: "critical",
          actual: "critical",
          matched: true,
        },
      ],
      would_actions: ["уведомление (role) «Инцидент»"],
    });
    renderPage();
    await screen.findAllByText("Критичные инциденты");

    fireEvent.change(screen.getByLabelText("Правило"), {
      target: { value: "r1" },
    });
    fireEvent.change(screen.getByLabelText("Payload события (JSON)"), {
      target: { value: '{"severity": "critical"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Проверить" }));

    expect(await screen.findByText("Совпадает")).toBeInTheDocument();
    expect(rulesApi.dryRun).toHaveBeenCalledWith(
      expect.objectContaining({
        rule: expect.objectContaining({
          name: "Критичные инциденты",
          event_type: "IncidentCreated",
        }),
        event: {
          event_type: "IncidentCreated",
          payload: { severity: "critical" },
        },
      }),
    );
    expect(
      screen.getByText("уведомление (role) «Инцидент»"),
    ).toBeInTheDocument();
  });

  it("renders the trigger log with status badge and outcomes", async () => {
    renderPage();
    expect(await screen.findByText("Успех")).toBeInTheDocument();
    expect(screen.getByText("Уведомление: создано")).toBeInTheDocument();
  });
});
