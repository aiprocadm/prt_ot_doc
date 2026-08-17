import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ClientChangePage,
  CrossClientAttention,
  CrossClientCalendar,
  PortfolioPage,
  SpecialistWorkloadResponse,
} from "@/api/managedClients";

const api = vi.hoisted(() => ({
  portfolio: vi.fn(),
  attention: vi.fn(),
  calendar: vi.fn(),
  workload: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  changes: vi.fn(),
  patchChangeStatus: vi.fn(),
  collectDqSignals: vi.fn(),
}));

vi.mock("@/api/managedClients", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  managedClientsApi: api,
}));

import ClientCockpitPage from "@/pages/managed-clients/ClientCockpitPage";

const PORTFOLIO: PortfolioPage = {
  items: [
    {
      id: "mc1",
      name: "ООО Ромашка",
      mode: "lightweight",
      company_id: "comp-a",
      dedicated_tenant_slug: null,
      contract_status: "active",
      contract_no: "Д-1",
      contract_starts_at: null,
      contract_ends_at: "2026-08-09",
      responsible_person_id: null,
      notes: null,
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
      contract_days_left: 5,
      contract_expiring: true,
    },
    {
      id: "mc2",
      name: "АО Крупный",
      mode: "dedicated",
      company_id: null,
      dedicated_tenant_slug: "krupny",
      contract_status: "draft",
      contract_no: null,
      contract_starts_at: null,
      contract_ends_at: null,
      responsible_person_id: null,
      notes: null,
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
      contract_days_left: null,
      contract_expiring: false,
    },
  ],
  summary: {
    total: 2,
    active: 1,
    draft: 1,
    suspended: 0,
    terminated: 0,
    lightweight: 1,
    dedicated: 1,
    contracts_expiring: 1,
  },
  total: 2,
  limit: 100,
  offset: 0,
};

const ATTENTION: CrossClientAttention = {
  generated_at: "2026-08-04T10:00:00Z",
  summary: {
    clients_total: 2,
    clients_with_signals: 1,
    clients_not_aggregated: 1,
    signals_total: 4,
    critical_clients: 1,
  },
  items: [
    {
      client_id: "mc1",
      client_name: "ООО Ромашка",
      aggregation: "aggregated",
      signals: [
        {
          kind: "medical_overdue",
          count: 3,
          severity: "critical",
          title: "Просроченные медосмотры",
          action_hint: "Направьте сотрудников на медосмотр",
        },
        {
          kind: "contract_expiring",
          count: 1,
          severity: "high",
          title: "Истекает договор",
          action_hint: "Продлите договор",
        },
      ],
      total: 4,
      severity: "critical",
      reason: null,
    },
    {
      client_id: "mc2",
      client_name: "АО Крупный",
      aggregation: "not_aggregated",
      signals: [],
      total: null,
      severity: null,
      reason: "Данные ведутся в отдельном контуре клиента",
    },
  ],
};

const CALENDAR: CrossClientCalendar = {
  generated_at: "2026-08-04T10:00:00Z",
  horizon_days: 30,
  summary: {
    events_total: 2,
    overdue: 1,
    due_today: 0,
    upcoming: 1,
    clients_touched: 1,
  },
  days: [
    {
      due_date: "2026-08-01",
      overdue: true,
      events: [
        {
          kind: "medical",
          title: "Медосмотр",
          due_date: "2026-08-01",
          client_id: "mc1",
          client_name: "ООО Ромашка",
          subject: "Иванов Иван",
          responsible_person_id: null,
          days_left: -3,
          overdue: true,
        },
      ],
    },
    {
      due_date: "2026-08-09",
      overdue: false,
      events: [
        {
          kind: "contract",
          title: "Договор",
          due_date: "2026-08-09",
          client_id: "mc1",
          client_name: "ООО Ромашка",
          subject: "Д-1",
          responsible_person_id: null,
          days_left: 5,
          overdue: false,
        },
      ],
    },
  ],
};

const WORKLOAD: SpecialistWorkloadResponse = {
  generated_at: "2026-08-04T10:00:00Z",
  thresholds: { max_clients: 8, max_signals: 25, max_overdue: 10 },
  summary: { specialists_total: 1, overloaded: 1, clients_unassigned: 2 },
  items: [
    {
      person_id: "spec-1",
      person_name: "Иванов Иван",
      unassigned: false,
      clients_total: 3,
      clients_critical: 1,
      signals_total: 12,
      overdue_deadlines: 2,
      overloaded: true,
      overload_reasons: [
        {
          code: "critical_client",
          text: "Есть клиент в критическом состоянии",
        },
      ],
    },
    {
      person_id: "__unassigned__",
      person_name: null,
      unassigned: true,
      clients_total: 2,
      clients_critical: 0,
      signals_total: 3,
      overdue_deadlines: 0,
      overloaded: false,
      overload_reasons: [],
    },
  ],
};

const FEED: ClientChangePage = {
  items: [
    {
      id: "ch1",
      kind: "employee_hired",
      kind_title: "Принят новый сотрудник",
      happened_on: "2026-08-10",
      summary: "Принят: Петров Пётр",
      details: "Замечено при загрузке кадровых данных.",
      status: "new",
      handled_at: null,
      suggestions: ["Вводный и первичный инструктаж", "Направление на медосмотр"],
      source: "import",
    },
    {
      id: "ch2",
      kind: "deadline_approaching",
      kind_title: "Наступает срок",
      happened_on: "2026-08-01",
      summary: "Просрочен медосмотр: Иванов Иван",
      details: "Найдено проверкой качества данных.",
      status: "handled",
      handled_at: "2026-08-11T00:00:00Z",
      suggestions: ["Задача на продление"],
      source: "data_quality",
    },
  ],
  total: 2,
  summary: "Требуют внимания: 1 из 2",
};

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.portfolio.mockResolvedValue(PORTFOLIO);
  api.attention.mockResolvedValue(ATTENTION);
  api.calendar.mockResolvedValue(CALENDAR);
  api.workload.mockResolvedValue(WORKLOAD);
  api.create.mockResolvedValue({ id: "mc3" });
  api.changes.mockResolvedValue(FEED);
  api.patchChangeStatus.mockResolvedValue(FEED.items[0]);
  api.collectDqSignals.mockResolvedValue({
    found: 3,
    recorded: 1,
    already_in_feed: 1,
    not_client_related: 1,
    unparsed: 0,
    deferred: 0,
    truncated: false,
    summary:
      "Найдено просрочек: 3, записано в ленты: 1, уже в лентах: 1, не про клиентов: 1",
  });
});

describe("ClientCockpitPage", () => {
  it("показывает сводку внимания и сигналы клиента", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("attention-summary")).toBeInTheDocument(),
    );

    expect(screen.getByText("Просроченные медосмотры:")).toBeInTheDocument();
    expect(screen.getByText(/Критичных:/)).toBeInTheDocument();
  });

  it("клиент со своим контуром помечен «данные не собраны», а не нулём", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("attention-summary")).toBeInTheDocument(),
    );

    expect(screen.getByText("Данные не собраны")).toBeInTheDocument();
    expect(
      screen.getByText("Данные ведутся в отдельном контуре клиента"),
    ).toBeInTheDocument();
    // и он НЕ выдан за «без сигналов» — это разные вещи
    expect(screen.queryByText("Без сигналов")).not.toBeInTheDocument();
  });

  it("внимание идёт выше портфеля: окно открывают ради «где горит»", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("attention-summary")).toBeInTheDocument(),
    );

    const attention = screen.getByTestId("attention-summary");
    const portfolio = screen.getByTestId("portfolio-summary");
    // Node.compareDocumentPosition: 4 = attention идёт перед portfolio
    expect(
      attention.compareDocumentPosition(portfolio) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("в портфеле помечен истекающий договор", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("portfolio-summary")).toBeInTheDocument(),
    );

    expect(screen.getByText("Истекает")).toBeInTheDocument();
    // имя клиента есть и в блоке внимания, и в портфеле — проверяем именно таблицу
    const table = screen.getByTestId("portfolio-table");
    expect(within(table).getByText("ООО Ромашка")).toBeInTheDocument();
    expect(within(table).getByText("Свой контур")).toBeInTheDocument();
  });

  it("создаёт клиента и перезагружает окно", async () => {
    const user = userEvent.setup();
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("portfolio-summary")).toBeInTheDocument(),
    );

    await user.type(screen.getByLabelText("Название клиента"), "Новый клиент");
    await user.type(screen.getByLabelText("Организация клиента"), "comp-x");
    await user.click(screen.getByRole("button", { name: "Добавить клиента" }));

    await waitFor(() => expect(api.create).toHaveBeenCalled());
    expect(api.create.mock.calls[0][0]).toMatchObject({
      name: "Новый клиент",
      mode: "lightweight",
      company_id: "comp-x",
    });
    // после создания окно перечитывается
    await waitFor(() => expect(api.portfolio).toHaveBeenCalledTimes(2));
  });

  it("для своего контура спрашивает slug, а не организацию", async () => {
    const user = userEvent.setup();
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("portfolio-summary")).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByLabelText("Режим ведения"),
      "dedicated",
    );
    expect(screen.getByLabelText("Контур клиента")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Организация клиента"),
    ).not.toBeInTheDocument();
  });

  it("выключенный модуль объясняется, а не выглядит поломкой", async () => {
    api.portfolio.mockRejectedValue({
      status: 404,
      code: "MANAGED_CLIENTS_DISABLED",
    });
    api.attention.mockRejectedValue({
      status: 404,
      code: "MANAGED_CLIENTS_DISABLED",
    });

    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByText("Модуль не подключён")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("attention-summary")).not.toBeInTheDocument();
  });

  it("сбой одного блока не прячет второй", async () => {
    api.attention.mockRejectedValue({
      status: 500,
      message: "Внутренняя ошибка",
    });

    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("portfolio-summary")).toBeInTheDocument(),
    );
    // имя встречается ещё в фильтре календаря — проверяем именно таблицу портфеля
    expect(
      within(screen.getByTestId("portfolio-table")).getByText("ООО Ромашка"),
    ).toBeInTheDocument();
  });

  it("показывает календарь дедлайнов с просрочкой", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("calendar-summary")).toBeInTheDocument(),
    );

    expect(screen.getByText(/Просрочено:/)).toBeInTheDocument();
    expect(screen.getAllByTestId("calendar-day")).toHaveLength(2);
    // просроченный день помечен
    expect(screen.getAllByText("Просрочено").length).toBeGreaterThan(0);
  });

  it("фильтр по типу перезапрашивает календарь", async () => {
    const user = userEvent.setup();
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("calendar-summary")).toBeInTheDocument(),
    );
    api.calendar.mockClear();

    await user.selectOptions(screen.getByLabelText("Тип"), "medical");
    await waitFor(() => expect(api.calendar).toHaveBeenCalled());
    expect(api.calendar.mock.calls.at(-1)?.[0]).toMatchObject({
      kind: ["medical"],
    });
  });

  it("фильтр «все типы» не шлёт лишний параметр", async () => {
    const user = userEvent.setup();
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("calendar-summary")).toBeInTheDocument(),
    );

    await user.selectOptions(screen.getByLabelText("Горизонт"), "7");
    await waitFor(() =>
      expect(api.calendar.mock.calls.at(-1)?.[0]).toMatchObject({ days: 7 }),
    );
    expect(api.calendar.mock.calls.at(-1)?.[0].kind).toBeUndefined();
  });

  it("показывает загрузку специалистов с причиной перегруза", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("workload-summary")).toBeInTheDocument(),
    );

    const table = screen.getByTestId("workload-table");
    expect(within(table).getByText("Иванов Иван")).toBeInTheDocument();
    expect(within(table).getByText("Перегруз")).toBeInTheDocument();
    expect(
      screen.getByText("Есть клиент в критическом состоянии"),
    ).toBeInTheDocument();
  });

  it("показывает пороги: «перегружен» без правила — повод для спора", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("workload-summary")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Порог перегруза/)).toBeInTheDocument();
  });

  it("клиенты без ответственного видны отдельной строкой", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("workload-summary")).toBeInTheDocument(),
    );

    expect(screen.getByText("Без ответственного")).toBeInTheDocument();
    expect(screen.getByText(/Без ответственного:/)).toBeInTheDocument();
    expect(screen.getAllByTestId("workload-row")).toHaveLength(2);
  });
});

describe("Лента изменений (BIZ-51)", () => {
  it("лента грузится по первому клиенту сама и показывает записи с подсказками", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("feed-table")).toBeInTheDocument(),
    );

    expect(api.changes).toHaveBeenCalledWith("mc1");
    expect(screen.getByTestId("feed-summary")).toHaveTextContent(
      "Требуют внимания: 1 из 2",
    );
    const table = within(screen.getByTestId("feed-table"));
    expect(table.getByText("Принят: Петров Пётр")).toBeInTheDocument();
    // Подсказки «что теперь делать» видны сразу — это смысл ленты.
    expect(
      table.getByText(/Вводный и первичный инструктаж/),
    ).toBeInTheDocument();
    // Источник подписан по-человечески: доверие к записям разное.
    expect(table.getByText("Импорт данных")).toBeInTheDocument();
    expect(table.getByText("Качество данных")).toBeInTheDocument();
  });

  it("смена клиента перезагружает ленту выбранного", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("feed-table")).toBeInTheDocument(),
    );

    await userEvent.selectOptions(
      screen.getByTestId("feed-client-select"),
      "mc2",
    );

    await waitFor(() => expect(api.changes).toHaveBeenCalledWith("mc2"));
  });

  it("«Разобрано» зовёт сервер и перечитывает ленту", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("feed-table")).toBeInTheDocument(),
    );
    api.changes.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Разобрано" }));

    await waitFor(() =>
      expect(api.patchChangeStatus).toHaveBeenCalledWith(
        "mc1",
        "ch1",
        "handled",
      ),
    );
    await waitFor(() => expect(api.changes).toHaveBeenCalled());
  });

  it("разобранная запись предлагает «Вернуть», а не повторный разбор", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("feed-table")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole("button", { name: "Вернуть" }));

    await waitFor(() =>
      expect(api.patchChangeStatus).toHaveBeenCalledWith("mc1", "ch2", "new"),
    );
  });

  it("сбор сигналов качества показывает честный итог НА ЭКРАНЕ", async () => {
    render(<ClientCockpitPage />);
    await waitFor(() =>
      expect(screen.getByTestId("feed-table")).toBeInTheDocument(),
    );
    api.changes.mockClear();

    await userEvent.click(screen.getByTestId("collect-dq-button"));

    await waitFor(() =>
      expect(screen.getByTestId("dq-collect-result")).toHaveTextContent(
        "не про клиентов: 1",
      ),
    );
    // После сбора лента перечитывается — новые записи видны без F5.
    await waitFor(() => expect(api.changes).toHaveBeenCalled());
  });

  it("пустая лента объяснена словами, а не пустым местом", async () => {
    api.changes.mockResolvedValue({
      items: [],
      total: 0,
      summary: "Изменений не зафиксировано",
    });
    render(<ClientCockpitPage />);

    await waitFor(() =>
      expect(
        screen.getAllByText(/Изменений не зафиксировано/).length,
      ).toBeGreaterThan(0),
    );
  });
});
