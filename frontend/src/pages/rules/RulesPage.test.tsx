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
  RecipientRoleOption,
  TriggerRead,
} from "@/types/dto/rules";

import RulesPage from "./RulesPage";

vi.mock("@/api/rules", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/rules")>();
  return {
    ...actual,
    rulesApi: {
      eventTypes: vi.fn(),
      recipientRoles: vi.fn(),
      list: vi.fn(),
      create: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      dryRun: vi.fn(),
      test: vi.fn(),
      triggers: vi.fn(),
      library: vi.fn(),
      installLibrary: vi.fn(),
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
  {
    event_type: "PPEReplacementDue",
    fields: [
      { name: "person_id", kind: "string" },
      { name: "item_name", kind: "string" },
    ],
  },
];

/** Срез-148: роли-получатели словами — как их отдаёт `GET /rules/recipient-roles`. */
const RECIPIENT_ROLES: RecipientRoleOption[] = [
  { code: "admin", label: "Администратор" },
  { code: "owner", label: "Владелец арендатора" },
  { code: "ot_specialist", label: "Специалист ОТ" },
  { code: "ecologist", label: "Эколог" },
  { code: "pb_engineer", label: "Инженер ПБ" },
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

// BIZ-54-57 срез-4: библиотека по дисциплинам. В наборе намеренно есть и
// дисциплина с правилами, и дисциплина без них — вторая обязана объясняться
// словами, а не нулём.
const LIBRARY = {
  total: 6,
  installed: 6,
  removed: 0,
  items: [
    {
      discipline: "fire_safety",
      title: "Пожарная безопасность",
      rules: 1,
      reason: "",
      missing: [],
      removed: [],
    },
    {
      discipline: "ecology",
      title: "Экология",
      rules: 0,
      reason: "в системе нет ни одного события экологии",
      missing: [],
      removed: [],
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(rulesApi.list).mockResolvedValue({
    items: [RULE],
    total: 1,
    limit: 100,
    offset: 0,
  });
  vi.mocked(rulesApi.eventTypes).mockResolvedValue({
    items: EVENT_TYPES,
    total: EVENT_TYPES.length,
  });
  vi.mocked(rulesApi.recipientRoles).mockResolvedValue({
    items: RECIPIENT_ROLES,
    total: RECIPIENT_ROLES.length,
  });
  vi.mocked(rulesApi.triggers).mockResolvedValue({
    items: [TRIGGER],
    total: 1,
    limit: 50,
    offset: 0,
  });
  vi.mocked(rulesApi.library).mockResolvedValue(LIBRARY);
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
    vi.mocked(rulesApi.list).mockRejectedValue(FEATURE_OFF_ERROR);
    vi.mocked(rulesApi.eventTypes).mockRejectedValue(FEATURE_OFF_ERROR);
    vi.mocked(rulesApi.triggers).mockRejectedValue(FEATURE_OFF_ERROR);
    renderPage();
    expect(await screen.findByText("Функция недоступна")).toBeInTheDocument();
  });

  it("creates a rule through the form dialog", async () => {
    vi.mocked(rulesApi.create).mockResolvedValue({
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
    // Роли приходят с сервера (срез-148) — ждём галочку, а не берём из кода формы.
    fireEvent.click(await within(actionCard).findByLabelText("Администратор"));
    fireEvent.change(
      within(actionCard).getByLabelText("Заголовок уведомления"),
      { target: { value: "Заголовок" } },
    );
    fireEvent.change(within(actionCard).getByLabelText("Текст уведомления"), {
      target: { value: "Текст" },
    });

    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(rulesApi.create).toHaveBeenCalled());
    const [payload] = vi.mocked(rulesApi.create).mock.calls[0];
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

  it("роли получателей — со словаря сервера, роль правила вне словаря не теряется (срез-148)", async () => {
    vi.mocked(rulesApi.list).mockResolvedValue({
      items: [
        {
          ...RULE,
          actions_json: [
            {
              ...RULE.actions_json[0],
              recipient_mode: "role",
              roles: ["ecologist", "inspector_contractor"],
            },
          ],
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    });
    vi.mocked(rulesApi.update).mockResolvedValue(RULE);
    renderPage();
    await screen.findAllByText("Критичные инциденты");

    fireEvent.click(
      (await screen.findAllByRole("button", { name: "Изменить" }))[0],
    );
    const dialog = await screen.findByRole("dialog");
    expect(rulesApi.recipientRoles).toHaveBeenCalled();
    const actionCard = within(dialog).getByTestId("action-card-0");
    // Получатель библиотечного правила — эколог — виден и отмечен; прежний
    // список из кода формы его не знал вовсе.
    expect(await within(actionCard).findByLabelText("Эколог")).toBeChecked();
    expect(within(actionCard).getByLabelText("Инженер ПБ")).not.toBeChecked();
    // Роль, которой в словаре нет (псевдоним), показана кодом и не потеряна.
    expect(
      within(actionCard).getByLabelText("inspector_contractor"),
    ).toBeChecked();
    // Список — только с сервера: роли, которых он не прислал, не рисуются.
    expect(
      within(actionCard).queryByLabelText("Линейный руководитель"),
    ).not.toBeInTheDocument();

    fireEvent.click(within(actionCard).getByLabelText("Инженер ПБ"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(rulesApi.update).toHaveBeenCalled());
    const [id, payload] = vi.mocked(rulesApi.update).mock.calls[0];
    expect(id).toBe("r1");
    expect(payload).toMatchObject({
      actions_json: [
        expect.objectContaining({
          recipient_mode: "role",
          roles: ["ecologist", "inspector_contractor", "pb_engineer"],
        }),
      ],
    });
  });

  it("submits boolean-field condition values as real booleans, not strings", async () => {
    vi.mocked(rulesApi.create).mockResolvedValue({
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
    const [payload] = vi.mocked(rulesApi.create).mock.calls[0];
    // Строгая проверка: настоящий boolean true, не строка "true".
    expect(payload.conditions_json.conditions?.[0]).toEqual({
      field: "overdue",
      op: "eq",
      value: true,
    });
    expect(payload.actions_json).toEqual([{ type: "webhook" }]);
  });

  it("runs a dry-run and shows the matched badge", async () => {
    vi.mocked(rulesApi.dryRun).mockResolvedValue({
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

  it("показывает библиотеку по дисциплинам и объясняет пустые (BIZ-54-57)", async () => {
    renderPage();

    const library = await screen.findByTestId("rule-library");
    expect(
      within(library).getByText(/Пожарная безопасность/),
    ).toBeInTheDocument();
    // Ноль без причины прочитали бы как недоделку, а не как решение.
    expect(
      within(library).getByText(
        /правил нет — в системе нет ни одного события экологии/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/выдано 6 из 6/)).toBeInTheDocument();
  });

  it("выдаёт недостающие правила библиотеки и перечитывает экран (срез-63)", async () => {
    vi.mocked(rulesApi.library).mockResolvedValue({
      ...LIBRARY,
      total: 12,
      installed: 6,
    });
    vi.mocked(rulesApi.installLibrary).mockResolvedValue({
      created: ["БДД: истёк срок водительского удостоверения"],
      kept_deleted: [],
      installed: 12,
      total: 12,
    });
    renderPage();

    const button = await screen.findByRole("button", {
      name: /Выдать недостающие \(6\)/,
    });
    expect(rulesApi.list).toHaveBeenCalledTimes(1);
    fireEvent.click(button);

    await waitFor(() => expect(rulesApi.installLibrary).toHaveBeenCalled());
    // После выдачи экран обязан перечитать и реестр правил, и библиотеку:
    // иначе «выдано 6 из 12» так и висело бы.
    await waitFor(() => expect(rulesApi.list).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(rulesApi.library).toHaveBeenCalledTimes(2));
  });

  it("удалённые специалистом правила названы числом, а кнопки без недостающих нет", async () => {
    vi.mocked(rulesApi.library).mockResolvedValue({
      ...LIBRARY,
      total: 12,
      installed: 10,
      removed: 2,
    });
    renderPage();

    await screen.findByTestId("rule-library");
    expect(screen.getByTestId("rule-library-removed")).toHaveTextContent(
      "удалено вами: 2",
    );
    // 10 + 2 = 12: ни разу не выданных нет — кнопка, которая ничего не
    // сделает, хуже отсутствующей.
    expect(
      screen.queryByRole("button", { name: /Выдать недостающие/ }),
    ).not.toBeInTheDocument();
    // Событие сроков названо словами, а не кодом.
    expect(screen.getByText(/«Срок дисциплины просрочен»/)).toBeInTheDocument();
  });

  it("в строке дисциплины названы имена не выданных и удалённых правил (срез-66)", async () => {
    vi.mocked(rulesApi.library).mockResolvedValue({
      ...LIBRARY,
      total: 12,
      installed: 10,
      removed: 1,
      items: [
        {
          discipline: "road_safety",
          title: "БДД",
          rules: 2,
          reason: "",
          missing: ["БДД: истёк срок водительского удостоверения"],
          removed: [],
        },
        {
          discipline: "medical",
          title: "Медосмотры",
          rules: 2,
          reason: "",
          missing: [],
          removed: ["Медосмотр: заключение «не годен» — отстранить"],
        },
      ],
    });
    renderPage();

    await screen.findByTestId("rule-library");
    // Не выдано — это заведёт кнопка; число в кнопке сходится с именами.
    expect(
      screen.getByTestId("rule-library-missing-road_safety"),
    ).toHaveTextContent(
      "не выдано: БДД: истёк срок водительского удостоверения",
    );
    expect(
      screen.getByRole("button", { name: /Выдать недостающие \(1\)/ }),
    ).toBeInTheDocument();
    // Удалено вами — кнопка не тронет; у строки без удалённых подписи нет.
    expect(
      screen.getByTestId("rule-library-removed-medical"),
    ).toHaveTextContent(
      "удалено вами: Медосмотр: заключение «не годен» — отстранить",
    );
    expect(
      screen.queryByTestId("rule-library-missing-medical"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("rule-library-removed-road_safety"),
    ).not.toBeInTheDocument();
  });

  it("ошибка библиотеки не гасит реестр правил", async () => {
    vi.mocked(rulesApi.library).mockRejectedValue({
      status: 500,
      message: "boom",
    });
    renderPage();

    expect(
      (await screen.findAllByText("Критичные инциденты")).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByTestId("rule-library")).not.toBeInTheDocument();
  });

  it("получатель «работник из события» есть только у событий с работником", async () => {
    // Срез-118: у события без person_id такое правило никогда бы не нашло
    // адресата — вариант не показываем, а выбранный ранее сбрасываем.
    vi.mocked(rulesApi.create).mockResolvedValue({
      ...RULE,
      id: "r5",
      name: "Работнику",
    });
    renderPage();
    await screen.findAllByText("Критичные инциденты");

    fireEvent.click(screen.getByRole("button", { name: "Новое правило" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Имя"), {
      target: { value: "Работнику" },
    });
    fireEvent.change(within(dialog).getByLabelText("Событие"), {
      target: { value: "IncidentCreated" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Добавить действие" }),
    );
    const actionCard = within(dialog).getByTestId("action-card-0");
    fireEvent.change(within(actionCard).getByLabelText("Тип действия"), {
      target: { value: "notify" },
    });
    const recipient = within(actionCard).getByLabelText(
      "Получатель",
    ) as HTMLSelectElement;
    expect(
      within(recipient).queryByRole("option", { name: "Работник из события" }),
    ).not.toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText("Событие"), {
      target: { value: "PPEReplacementDue" },
    });
    expect(
      within(recipient).getByRole("option", { name: "Работник из события" }),
    ).toBeInTheDocument();
    fireEvent.change(recipient, { target: { value: "person" } });
    expect(recipient.value).toBe("person");

    // Возврат на событие без работника не должен оставить непроходной режим.
    fireEvent.change(within(dialog).getByLabelText("Событие"), {
      target: { value: "IncidentCreated" },
    });
    expect(recipient.value).toBe("actor");

    fireEvent.change(within(dialog).getByLabelText("Событие"), {
      target: { value: "PPEReplacementDue" },
    });
    fireEvent.change(recipient, { target: { value: "person" } });
    fireEvent.change(
      within(actionCard).getByLabelText("Заголовок уведомления"),
      { target: { value: "Замена СИЗ" } },
    );
    fireEvent.change(within(actionCard).getByLabelText("Текст уведомления"), {
      target: { value: "Срок по {item_name}" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(rulesApi.create).toHaveBeenCalled());
    const [payload] = vi.mocked(rulesApi.create).mock.calls[0];
    expect(payload.event_type).toBe("PPEReplacementDue");
    expect(payload.actions_json[0]).toMatchObject({
      type: "notify",
      recipient_mode: "person",
      title_template: "Замена СИЗ",
    });
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // Срез добавил экрану блок — приёмка бюджета обязана пройти вместе с ним.
    renderPage();
    await screen.findByTestId("rule-library");

    const { uxBudgetDelta } = await import("@/test-utils/uxBudget");
    const budget = uxBudgetDelta(document.body, "RulesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
