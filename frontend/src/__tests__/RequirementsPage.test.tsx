import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
    post: (...args: unknown[]) => apiClientMock.post(...args),
    patch: (...args: unknown[]) => apiClientMock.patch(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import RequirementsPage, { dueLabel } from "@/pages/npa/RequirementsPage";
import { useNpaStore } from "@/stores/npa";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import type {
  ComplianceRequirementDto,
  ComplianceRequirementListDto,
  ComplianceRequirementOptionsDto,
} from "@/types/dto/complianceRequirements";
import type { NpaDto } from "@/types/dto/npa";

/**
 * Срез-145 (B.18 разд. 19.2): реестр требований — обязательное ядро.
 * Срез-147: справочники формы (ответственный, площадка, роль) — своей ручкой,
 * правка требования с экрана.
 *
 * Фикстуры списаны с ответа сервера (`backend/app/schemas/compliance_requirements.py`):
 * «просрочено», «дней осталось» и имена приходят готовыми, витрина их не считает.
 */

const acts: NpaDto[] = [
  {
    id: "npa-1",
    code: "772н",
    title: "Приказ Минтруда № 772н об обучении по охране труда",
    edition: "ред. от 01.03.2026",
    valid_from: "2026-03-01",
    valid_to: null,
    clauses: [{ id: "c-1", code: "п. 4", text: "Периодичность обучения" }],
  },
];

const overdueItem: ComplianceRequirementDto = {
  id: "req-1",
  code: "OT-01",
  title: "Обучение по охране труда руководителей",
  description: null,
  npa_id: "npa-1",
  npa_code: "772н",
  npa_title: "Приказ Минтруда № 772н об обучении по охране труда",
  clause_id: "c-1",
  clause_code: "п. 4",
  role_code: "line_manager",
  role_label: "Линейный руководитель",
  site_id: "site-1",
  site_name: "Цех №1",
  process_code: null,
  owner_user_id: "u-1",
  owner_name: "Иванова Мария",
  periodicity_days: 365,
  next_due_at: "2026-01-15",
  last_confirmed_at: "2025-01-15",
  severity: "critical",
  status: "active",
  retired_at: null,
  overdue: true,
  days_left: -40,
  evidence_count: 1,
  created_at: "2025-01-15T10:00:00Z",
  updated_at: "2025-01-15T10:00:00Z",
};

const dueSoonItem: ComplianceRequirementDto = {
  ...overdueItem,
  id: "req-2",
  code: "OT-02",
  title: "Специальная оценка условий труда",
  clause_id: null,
  clause_code: null,
  role_code: null,
  role_label: null,
  site_id: null,
  site_name: null,
  owner_user_id: null,
  owner_name: null,
  periodicity_days: null,
  next_due_at: "2026-03-01",
  last_confirmed_at: null,
  severity: "medium",
  overdue: false,
  days_left: 2,
  evidence_count: 0,
};

const listResponse = (
  canManage: boolean,
  items: ComplianceRequirementDto[] = [overdueItem, dueSoonItem],
  // Срез-195: счётчики приходят по ВСЕЙ выборке, а не по странице. Умолчание
  // «сколько отдали» годится для проверок, где страница одна; проверка самого
  // листателя передаёт число больше длины списка — именно так это и выглядит
  // на второй странице.
  totals: { total?: number; limit?: number; offset?: number } = {},
): ComplianceRequirementListDto => ({
  items,
  total: totals.total ?? items.length,
  active: items.filter((item) => item.status === "active").length,
  overdue: items.filter((item) => item.overdue).length,
  can_manage: canManage,
  limit: totals.limit ?? 50,
  offset: totals.offset ?? 0,
});

const tenantDocuments = [
  {
    id: "doc-1",
    name: "Протокол обучения",
    type: "document",
    company: { id: "c-1", name: "ООО Ромашка" },
    status: "ready",
    version: "1",
  },
];

/** Справочник формы — как его отдаёт `GET /compliance/requirements/options`. */
const formOptions: ComplianceRequirementOptionsDto = {
  owners: [
    {
      id: "u-1",
      name: "Иванова Мария",
      role: "ot_specialist",
      role_label: "Специалист ОТ",
    },
    {
      id: "u-2",
      name: "Петров Пётр",
      role: "worker",
      role_label: "Рабочий / сотрудник",
    },
  ],
  sites: [
    { id: "site-1", name: "Цех №1", company_name: "ООО Ромашка" },
    { id: "site-2", name: "Склад", company_name: "ООО Ромашка" },
  ],
  roles: [
    { code: "ot_specialist", label: "Специалист ОТ" },
    { code: "line_manager", label: "Линейный руководитель" },
    { code: "worker", label: "Рабочий / сотрудник" },
  ],
  // Срез-196: процесс выбирается из словаря дисциплин, а не впечатывается.
  processes: [
    { code: "training", label: "Обучение" },
    { code: "fire_safety", label: "Пожарная безопасность" },
    { code: "occupational_safety", label: "Общая охрана труда" },
  ],
};

describe("RequirementsPage", () => {
  const mockRegistry = (
    canManage: boolean,
    items: ComplianceRequirementDto[] = [overdueItem, dueSoonItem],
  ) => {
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({ data: { items: acts, can_manage: false } });
      }
      if (url === "/compliance/requirements") {
        return Promise.resolve({ data: listResponse(canManage, items) });
      }
      if (url === "/compliance/requirements/options") {
        return Promise.resolve({ data: formOptions });
      }
      if (url === "/documents") {
        return Promise.resolve({ data: { items: tenantDocuments } });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
  };

  const renderPage = async (entry = "/npa/requirements") => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={[entry]}>
          <RequirementsPage />
        </MemoryRouter>,
      );
    });
    expect(
      await screen.findByText("Обучение по охране труда руководителей"),
    ).toBeInTheDocument();
  };

  beforeEach(() => {
    apiClientMock.get.mockReset();
    apiClientMock.post.mockReset();
    apiClientMock.patch.mockReset();
    useNpaStore.getState().reset();
    mockRegistry(false);
  });

  it("срок строкой: просрочка, «через N дн.», разовое без даты, снятое", () => {
    expect(dueLabel(overdueItem)).toBe("15.01.2026 · просрочено на 40 дн.");
    expect(dueLabel(dueSoonItem)).toBe("01.03.2026 · через 2 дн.");
    expect(dueLabel({ ...dueSoonItem, days_left: 0 })).toBe(
      "01.03.2026 · сегодня",
    );
    expect(dueLabel({ ...dueSoonItem, next_due_at: null })).toBe("без срока");
    expect(dueLabel({ ...dueSoonItem, status: "retired" })).toBe(
      "снято с контроля",
    );
  });

  it("рядовая роль видит свои требования без кнопок и в UX-бюджете", async () => {
    await renderPage();

    expect(screen.getByTestId("requirements-summary")).toHaveTextContent(
      "Всего: 2 · на контроле: 2 · просрочено: 1",
    );
    const rows = screen.getAllByTestId("requirement-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-overdue", "true");
    expect(
      within(rows[0]).getByText("15.01.2026 · просрочено на 40 дн."),
    ).toBeInTheDocument();
    expect(within(rows[0]).getByText("критическая")).toBeInTheDocument();
    // Срез-147: к чему относится — словами, а не кодом и не колонками.
    expect(within(rows[0]).getByText("площадка: Цех №1")).toBeInTheDocument();
    expect(
      within(rows[0]).getByText("роль: Линейный руководитель"),
    ).toBeInTheDocument();
    expect(within(rows[0]).getByText("доказательств: 1")).toBeInTheDocument();
    expect(within(rows[0]).getByText("ежегодно")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Иванова Мария")).toBeInTheDocument();
    expect(
      within(rows[0]).getByRole("link", { name: "772н · п. 4" }),
    ).toHaveAttribute("href", "/npa?selected=npa-1");
    expect(within(rows[1]).getByText("разово")).toBeInTheDocument();
    expect(within(rows[1]).queryByText(/площадка:/)).not.toBeInTheDocument();

    // Право писать приходит с сервера: без него ни кнопки, ни колонки.
    expect(
      screen.queryByRole("button", { name: "Добавить требование" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Действия")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Исполнено" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Изменить" }),
    ).not.toBeInTheDocument();
    // Справочник формы рядовой роли не запрашивается — ей нечего заводить.
    expect(apiClientMock.get).not.toHaveBeenCalledWith(
      "/compliance/requirements/options",
    );

    const budget = uxBudgetDelta(document.body, "RequirementsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("ссылка с экрана НПА `?npa_id=` фильтрует по акту и ведёт обратно", async () => {
    await renderPage("/npa/requirements?npa_id=npa-1");

    // Срез-195: к фильтру добавились страницы. Проверка сравнивает ПОЛНЫЙ
    // набор параметров намеренно — так видно, если запрос однажды потеряет
    // фильтр или уедет не на ту страницу.
    expect(apiClientMock.get).toHaveBeenCalledWith("/compliance/requirements", {
      params: { npa_id: "npa-1", limit: 50, offset: 0 },
    });
    expect(
      within(screen.getByTestId("requirements-summary")).getByRole("link", {
        name: "772н",
      }),
    ).toHaveAttribute("href", "/npa?selected=npa-1");
  });

  it("специалист заводит требование: акт, пункт, ответственный, площадка и роль — из справочника (срез-145/147)", async () => {
    mockRegistry(true);
    apiClientMock.post.mockImplementation((url: string, body: unknown) => {
      if (url === "/compliance/requirements") {
        const payload = body as { code: string; title: string };
        mockRegistry(true, [
          overdueItem,
          dueSoonItem,
          {
            ...dueSoonItem,
            id: "req-3",
            code: payload.code,
            title: payload.title,
          },
        ]);
        return Promise.resolve({ data: { id: "req-3", ...payload } });
      }
      throw new Error(`Unexpected POST ${url}`);
    });
    const user = userEvent.setup();
    await renderPage();

    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: "Добавить требование" }),
      );
    });
    // Справочник формы запрошен своей ручкой, а не админской `/admin/users`.
    expect(apiClientMock.get).toHaveBeenCalledWith(
      "/compliance/requirements/options",
    );
    expect(apiClientMock.get).not.toHaveBeenCalledWith(
      "/admin/users",
      expect.anything(),
    );
    // Открытая форма — тоже экран: первого уровня полей столько, сколько
    // разрешает бюджет; ответственный, площадка, роль, процесс — под «Дополнительно».
    const withDialog = uxBudgetDelta(document.body, "RequirementsPage");
    expect(withDialog.unexpected).toEqual([]);

    await user.type(screen.getByLabelText("Код"), "OT-03");
    await user.type(
      screen.getByLabelText("Требование"),
      "Инструктаж на рабочем месте",
    );
    await user.selectOptions(screen.getByLabelText("Серьёзность"), "high");
    await user.selectOptions(screen.getByLabelText("Нормативный акт"), "npa-1");
    await user.type(screen.getByLabelText("Периодичность, дней"), "180");
    await user.type(screen.getByLabelText("Контрольная дата"), "2999-01-01");
    await user.click(screen.getByText("Дополнительно"));
    await user.selectOptions(screen.getByLabelText("Пункт акта"), "c-1");
    // Люди, площадки и роли — словами: «Петров Пётр · Рабочий / сотрудник».
    await user.selectOptions(
      screen.getByLabelText("Ответственный"),
      screen.getByRole("option", { name: "Петров Пётр · Рабочий / сотрудник" }),
    );
    await user.selectOptions(
      screen.getByLabelText("Площадка"),
      screen.getByRole("option", { name: "Склад · ООО Ромашка" }),
    );
    await user.selectOptions(
      screen.getByLabelText("Роль"),
      screen.getByRole("option", { name: "Рабочий / сотрудник" }),
    );
    // Срез-196: процесс ВЫБИРАЕТСЯ из словаря дисциплин. До среза это было
    // поле для ввода с подсказкой-жаргоном, и «обучение» с «Обучение» были
    // разными процессами — сроки требований не попадали ни в один
    // дисциплинарный отчёт.
    await user.selectOptions(
      screen.getByLabelText("Процесс"),
      screen.getByRole("option", { name: "Обучение" }),
    );

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Добавить" }));
    });

    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/compliance/requirements",
      {
        code: "OT-03",
        title: "Инструктаж на рабочем месте",
        npa_id: "npa-1",
        clause_id: "c-1",
        periodicity_days: 180,
        next_due_at: "2999-01-01",
        severity: "high",
        description: null,
        role_code: "worker",
        site_id: "site-2",
        process_code: "training",
        owner_user_id: "u-2",
      },
    );
    // Список перечитан с сервера — новая строка на экране.
    expect(
      await screen.findByText("Инструктаж на рабочем месте"),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId("requirement-row")).toHaveLength(3);
  });

  it("«Изменить» открывает форму с текущими значениями и шлёт PATCH без кода (срез-147)", async () => {
    mockRegistry(true);
    apiClientMock.patch.mockImplementation((url: string, body: unknown) => {
      if (url === "/compliance/requirements/req-1") {
        const payload = body as { title: string; site_id: string | null };
        mockRegistry(true, [
          {
            ...overdueItem,
            title: payload.title,
            site_id: payload.site_id,
            site_name: payload.site_id ? "Склад" : null,
          },
          dueSoonItem,
        ]);
        return Promise.resolve({ data: { id: "req-1", ...payload } });
      }
      throw new Error(`Unexpected PATCH ${url}`);
    });
    const user = userEvent.setup();
    await renderPage();

    const [first] = screen.getAllByTestId("requirement-row");
    await act(async () => {
      await user.click(within(first).getByRole("button", { name: "Изменить" }));
    });
    expect(
      screen.getByRole("heading", { name: "Изменить требование OT-01" }),
    ).toBeInTheDocument();
    // Код — ключ: показан, но не правится.
    const codeInput = screen.getByLabelText("Код");
    expect(codeInput).toHaveValue("OT-01");
    expect(codeInput).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Требование")).toHaveValue(
      "Обучение по охране труда руководителей",
    );
    expect(screen.getByLabelText("Периодичность, дней")).toHaveValue(365);
    expect(screen.getByLabelText("Контрольная дата")).toHaveValue("2026-01-15");
    await user.click(screen.getByText("Дополнительно"));
    expect(screen.getByLabelText("Ответственный")).toHaveValue("u-1");
    expect(screen.getByLabelText("Площадка")).toHaveValue("site-1");
    expect(screen.getByLabelText("Роль")).toHaveValue("line_manager");

    await user.clear(screen.getByLabelText("Требование"));
    await user.type(
      screen.getByLabelText("Требование"),
      "Обучение руководителей и специалистов",
    );
    await user.selectOptions(screen.getByLabelText("Площадка"), "site-2");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Сохранить" }));
    });

    expect(apiClientMock.patch).toHaveBeenCalledWith(
      "/compliance/requirements/req-1",
      {
        title: "Обучение руководителей и специалистов",
        npa_id: "npa-1",
        clause_id: "c-1",
        periodicity_days: 365,
        next_due_at: "2026-01-15",
        severity: "critical",
        description: null,
        role_code: "line_manager",
        site_id: "site-2",
        process_code: null,
        owner_user_id: "u-1",
      },
    );
    expect(apiClientMock.post).not.toHaveBeenCalled();
    expect(
      await screen.findByText("Обучение руководителей и специалистов"),
    ).toBeInTheDocument();
    expect(screen.getByText("площадка: Склад")).toBeInTheDocument();
  });

  it("«Исполнено» шлёт доказательство, «Снять с контроля» — retire (срез-145)", async () => {
    mockRegistry(true);
    apiClientMock.post.mockImplementation((url: string) => {
      if (url === "/compliance/requirements/req-1/evidence") {
        mockRegistry(true, [
          { ...overdueItem, overdue: false, days_left: 300, evidence_count: 2 },
          dueSoonItem,
        ]);
        return Promise.resolve({ data: { id: "req-1" } });
      }
      if (url === "/compliance/requirements/req-2/retire") {
        mockRegistry(true, [
          { ...overdueItem, overdue: false, days_left: 300, evidence_count: 2 },
          { ...dueSoonItem, status: "retired" },
        ]);
        return Promise.resolve({ data: { id: "req-2" } });
      }
      throw new Error(`Unexpected POST ${url}`);
    });
    const user = userEvent.setup();
    await renderPage();

    const [first, second] = screen.getAllByTestId("requirement-row");
    expect(screen.getByText("Действия")).toBeInTheDocument();

    await act(async () => {
      await user.click(
        within(first).getByRole("button", { name: "Исполнено" }),
      );
    });
    // Без документа и заметки подтверждать нечем — кнопка выключена.
    expect(screen.getByRole("button", { name: "Подтвердить" })).toBeDisabled();
    await user.selectOptions(
      await screen.findByLabelText("Документ-доказательство"),
      "doc-1",
    );
    await user.type(screen.getByLabelText("Заметка"), "Протокол № 7");
    await user.type(screen.getByLabelText("Дата исполнения"), "2026-02-01");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Подтвердить" }));
    });

    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/compliance/requirements/req-1/evidence",
      {
        document_id: "doc-1",
        note: "Протокол № 7",
        confirmed_at: "2026-02-01",
      },
    );
    expect(await screen.findByText("доказательств: 2")).toBeInTheDocument();
    expect(screen.getByTestId("requirements-summary")).toHaveTextContent(
      "просрочено: 0",
    );

    await act(async () => {
      await user.click(
        within(second).getByRole("button", { name: "Снять с контроля" }),
      );
    });
    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/compliance/requirements/req-2/retire",
    );
    // «снято с контроля» есть и в фильтре статуса — ищем в самой строке.
    const retiredRow = (await screen.findAllByTestId("requirement-row"))[1];
    expect(
      await within(retiredRow).findByText("снято с контроля"),
    ).toBeInTheDocument();
    // У снятой строки действий больше нет.
    expect(
      within(retiredRow).queryByRole("button", { name: "Исполнено" }),
    ).not.toBeInTheDocument();
    expect(
      within(retiredRow).queryByRole("button", { name: "Изменить" }),
    ).not.toBeInTheDocument();
  });

  it("пустой реестр объясняет, кто его ведёт", async () => {
    mockRegistry(false, []);
    await act(async () => {
      render(
        <MemoryRouter>
          <RequirementsPage />
        </MemoryRouter>,
      );
    });
    expect(await screen.findByText("Требований нет")).toBeInTheDocument();
    expect(
      screen.getByText(/Реестр требований ведёт специалист по охране труда/),
    ).toBeInTheDocument();
  });

  it("реестр листается, а счётчики остаются по всей выборке (срез-195)", async () => {
    // Сервер отдал ДВЕ строки из ста: так выглядит первая страница большого
    // реестра. Счётчики при этом про все сто — иначе человек, увидев «Всего: 2»,
    // решил бы, что требований всего два.
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({ data: { items: acts, can_manage: false } });
      }
      if (url === "/compliance/requirements") {
        return Promise.resolve({
          data: listResponse(false, [overdueItem, dueSoonItem], { total: 100 }),
        });
      }
      if (url === "/compliance/requirements/options") {
        return Promise.resolve({ data: formOptions });
      }
      if (url === "/documents") {
        return Promise.resolve({ data: { items: tenantDocuments } });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    await renderPage();

    expect(screen.getByTestId("requirements-summary")).toHaveTextContent(
      "Всего: 100",
    );
    const pager = screen.getByTestId("requirements-pager");
    expect(pager).toHaveTextContent("Показано 1–2 из 100");
    // На первой странице «Назад» недоступна: нажатие увело бы в минус.
    expect(screen.getByRole("button", { name: "Назад" })).toBeDisabled();

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Дальше" }));
    });

    const calls = apiClientMock.get.mock.calls.filter(
      (call) => call[0] === "/compliance/requirements",
    );
    const last = calls[calls.length - 1][1];
    expect(last.params.offset).toBe(50);
    expect(last.params.limit).toBe(50);
  });

  it("листателя нет, когда всё уместилось на одной странице", async () => {
    // Кнопки «Дальше» на реестре из двух строк — лишний шум: экран под
    // UX-бюджетом, и каждый элемент должен быть заслужен.
    await renderPage();
    expect(screen.queryByTestId("requirements-pager")).toBeNull();
  });

  it("смена фильтра возвращает на первую страницу", async () => {
    // Иначе человек, отфильтровавший до трёх строк, оставшись на пятой
    // странице, увидел бы пусто и решил, что ничего не нашлось.
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({ data: { items: acts, can_manage: false } });
      }
      if (url === "/compliance/requirements") {
        return Promise.resolve({
          data: listResponse(false, [overdueItem, dueSoonItem], { total: 100 }),
        });
      }
      if (url === "/compliance/requirements/options") {
        return Promise.resolve({ data: formOptions });
      }
      if (url === "/documents") {
        return Promise.resolve({ data: { items: tenantDocuments } });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    await renderPage();

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Дальше" }));
    });
    await act(async () => {
      await userEvent.click(screen.getByLabelText(/только просроченные/i));
    });

    const calls = apiClientMock.get.mock.calls.filter(
      (call) => call[0] === "/compliance/requirements",
    );
    const last = calls[calls.length - 1][1];
    expect(last.params.offset).toBe(0);
  });
});
