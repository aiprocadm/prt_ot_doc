import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
    post: (...args: unknown[]) => apiClientMock.post(...args),
    delete: (...args: unknown[]) => apiClientMock.delete(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import NpaPage from "@/pages/npa/NpaPage";
import { useNpaStore } from "@/stores/npa";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import type { NpaDto } from "@/types/dto/npa";

// Срез-141: фикстуры списаны с ответа сервера (`backend/app/schemas/npa.py`),
// а не с выдуманной формы с `issuer`/`status` — тест на такой форме проверял
// бы витрину, которую сервер никогда не наполнит.
const npaItems: NpaDto[] = [
  {
    id: "npa-1",
    code: "772н",
    title: "Приказ Минтруда № 772н об обучении по охране труда",
    edition: "ред. от 01.03.2026",
    valid_from: "2026-03-01",
    valid_to: null,
    clauses: [{ id: "c-1", code: "1", text: "Общие положения" }],
  },
  {
    id: "npa-2",
    code: "2464",
    title: "Постановление № 2464 о порядке обучения",
    edition: "ред. от 01.01.2026",
    valid_from: "2026-01-01",
    valid_to: null,
    clauses: [],
  },
  {
    id: "npa-3",
    code: "29н",
    title: "Приказ № 29н о медосмотрах",
    edition: "ред. от 01.09.2025",
    valid_from: "2025-09-01",
    valid_to: "2026-02-28",
    clauses: [],
  },
];

const npaDetail = {
  act: {
    id: "npa-1",
    code: "772н",
    title: "Приказ Минтруда № 772н об обучении по охране труда",
    edition: "ред. от 01.03.2026",
  },
  revisions: [
    {
      id: "rev-1",
      revision_code: "772н-2026-03",
      title: "Редакция с новыми программами обучения",
      effective_from: "2026-03-01",
      effective_to: null,
      change_summary: "Обновлены программы обучения",
      // Срез-198: состояние редакции приходит с сервера словами.
      status: "active",
      status_title: "Действует",
    },
    {
      id: "rev-next",
      revision_code: "772н-2027-01",
      title: "Редакция будущего года",
      effective_from: "2027-01-01",
      effective_to: null,
      change_summary: null,
      status: "upcoming",
      status_title: "Ещё не вступила в силу",
    },
  ],
  // Срез-142: связи приходят по одной и с именами (`binding_items`), сводка —
  // по ключам сервера (`documents`/`templates`/...), а не по выдуманным.
  bindings: {
    documents: ["doc-1", "doc-2"],
    templates: [],
    packages: [],
  },
  binding_items: [
    {
      id: "b-1",
      npa_id: "npa-1",
      entity_type: "document",
      entity_id: "doc-1",
      ref: "п. 4",
      title: "Инструкция по ОТ · ООО Ромашка",
    },
    {
      id: "b-2",
      npa_id: "npa-1",
      entity_type: "document",
      entity_id: "doc-2",
      ref: null,
      title: "Программа обучения · ООО Ромашка",
    },
  ],
  summary: {
    documents: 2,
    templates: 0,
    packages: 0,
  },
  // Срез-197: категории, которые платформа записывать не умеет, приходят
  // ПРИЧИНОЙ. Раньше они считались вечным нулём, экран их молча скрывал, и
  // человек читал отсутствие строки как «этот закон их не задевает».
  unrecorded: {
    risks: "Связь акта с карточкой риска не ведётся: риск — самостоятельная сущность",
    workflows: "Связь акта с маршрутом согласования не ведётся",
  },
  tasks_to_create: [
    {
      code: "npa-update-documents",
      title: "Актуализировать зависимости НПА: documents",
      count: 2,
    },
  ],
};

const tenantDocuments = [
  {
    id: "doc-3",
    name: "Положение о СУОТ",
    type: "document",
    company: { id: "c-1", name: "ООО Ромашка" },
    status: "ready",
    version: "1",
  },
];

describe("NpaPage", () => {
  beforeEach(() => {
    apiClientMock.get.mockReset();
    apiClientMock.post.mockReset();
    apiClientMock.delete.mockReset();
    useNpaStore.getState().reset();

    mockRegistry(false);
  });

  const mockRegistry = (canManage: boolean, items: NpaDto[] = npaItems) => {
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({ data: { items, can_manage: canManage } });
      }
      if (url === "/npa/npa-1") {
        return Promise.resolve({ data: npaDetail });
      }
      if (url === "/documents") {
        return Promise.resolve({ data: { items: tenantDocuments } });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
  };

  it("экран в UX-бюджете и со списком, и с открытым анализом влияния (BIZ-60)", async () => {
    // Наполненный реестр: таблица НПА на 5 колонок, фильтры, кнопки
    // детализации. Замер пустого экрана ничего не доказал бы — лимиты
    // ловятся на данных (колонки и повторяющиеся кнопки строятся циклом).
    const user = userEvent.setup();

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText(
        "Приказ Минтруда № 772н об обучении по охране труда",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Постановление № 2464 о порядке обучения"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "NpaPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);

    // Второе состояние: выбранный НПА подсвечен primary-кнопкой, справа
    // раскрыт анализ влияния (редакции, связанные сущности, база задач).
    // Именно здесь primary-кнопок становится две — замер обязан пройти и тут.
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "772н" }));
    });

    expect(await screen.findByText("772н-2026-03")).toBeInTheDocument();
    expect(
      screen.getByText("Инструкция по ОТ · ООО Ромашка"),
    ).toBeInTheDocument();
    expect(screen.getByText("Документ · п. 4")).toBeInTheDocument();
    expect(
      screen.getByText("Актуализировать зависимости НПА: documents · 2"),
    ).toBeInTheDocument();

    const withDetail = uxBudgetDelta(document.body, "NpaPage");
    expect(withDetail.unexpected).toEqual([]);
    expect(withDetail.stale).toEqual([]);
  });

  it("кнопку «Добавить акт» видит только владелец платформы (срез-141)", async () => {
    // Реестр общий; остальным ручка ответит 403 — кнопка, которая всегда
    // кончается отказом, хуже отсутствующей. Право приходит с сервера.
    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    expect(
      await screen.findByText("Постановление № 2464 о порядке обучения"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Добавить акт" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("утратил силу")).toBeInTheDocument();
  });

  it("владелец платформы заводит акт, и список перечитывается (срез-141)", async () => {
    mockRegistry(true);
    apiClientMock.post.mockImplementation((url: string, body: unknown) => {
      if (url === "/npa") {
        const payload = body as { code: string; clauses: unknown[] };
        mockRegistry(true, [
          ...npaItems,
          {
            id: "npa-4",
            code: payload.code,
            title: "Новый акт",
            edition: "ред. 1",
            valid_from: null,
            valid_to: null,
            clauses: [],
          },
        ]);
        return Promise.resolve({ data: { id: "npa-4", ...payload } });
      }
      throw new Error(`Unexpected POST ${url}`);
    });
    const user = userEvent.setup();

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    expect(
      await screen.findByText("Постановление № 2464 о порядке обучения"),
    ).toBeInTheDocument();
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Добавить акт" }));
    });

    // Открытая форма — тоже экран: полей первого уровня в ней столько,
    // сколько разрешает бюджет; срок окончания и пункты — под «Дополнительно».
    const withDialog = uxBudgetDelta(document.body, "NpaPage");
    expect(withDialog.unexpected).toEqual([]);

    await user.type(screen.getByLabelText("Номер"), "1/29");
    await user.type(screen.getByLabelText("Редакция"), "ред. 1");
    await user.type(screen.getByLabelText("Название"), "Новый акт");
    await user.click(screen.getByText("Дополнительно"));
    await user.type(
      screen.getByLabelText("Пункты"),
      "1 Общие положения{enter}2 Программы обучения",
    );

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Добавить" }));
    });

    expect(apiClientMock.post).toHaveBeenCalledWith("/npa", {
      code: "1/29",
      title: "Новый акт",
      edition: "ред. 1",
      valid_from: null,
      valid_to: null,
      clauses: [
        { code: "1", text: "Общие положения" },
        { code: "2", text: "Программы обучения" },
      ],
    });
    // И в таблице, и среди кнопок детализации — список перечитан с сервера.
    expect(await screen.findAllByText("1/29")).toHaveLength(2);
  });

  it("ссылка из поиска `/npa?selected=` открывает детализацию (срез-142)", async () => {
    // Поисковый снимок ведёт на акт именно так; без разбора адреса ссылка
    // открывала бы пустую правую колонку.
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/npa?selected=npa-1"]}>
          <NpaPage />
        </MemoryRouter>,
      );
    });

    expect(await screen.findByText("772н-2026-03")).toBeInTheDocument();
    expect(
      screen.getByText("Программа обучения · ООО Ромашка"),
    ).toBeInTheDocument();
  });

  it("документ привязывается из списка документов, связь снимается (срез-142)", async () => {
    apiClientMock.post.mockImplementation((url: string, body: unknown) => {
      if (url === "/npa/npa-1/bindings") {
        return Promise.resolve({
          data: {
            id: "b-3",
            npa_id: "npa-1",
            title: "Положение о СУОТ",
            ...(body as object),
          },
        });
      }
      throw new Error(`Unexpected POST ${url}`);
    });
    apiClientMock.delete.mockResolvedValue({ data: null });
    const user = userEvent.setup();

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/npa?selected=npa-1"]}>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    expect(await screen.findByText("772н-2026-03")).toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: "Привязать документ" }),
      );
    });
    // Список документов — с той же ручки, что экран «Документы».
    expect(
      await screen.findByRole("option", {
        name: "Положение о СУОТ · ООО Ромашка",
      }),
    ).toBeInTheDocument();
    const withDialog = uxBudgetDelta(document.body, "NpaPage");
    expect(withDialog.unexpected).toEqual([]);

    await user.selectOptions(screen.getByLabelText("Документ"), "doc-3");
    await user.type(screen.getByLabelText("Пункт акта"), "п. 7");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Привязать" }));
    });

    // Срез-197: у связи появилась ОБЛАСТЬ ДЕЙСТВИЯ («кого и где касается»).
    // Здесь она не выбрана — и это законное состояние «весь акт», поэтому
    // контекст уходит пустым, а не отсутствует.
    expect(apiClientMock.post).toHaveBeenCalledWith("/npa/npa-1/bindings", {
      entity_type: "document",
      entity_id: "doc-3",
      ref: "п. 7",
      context: {},
    });
    // После привязки детализация перечитана с сервера.
    expect(
      apiClientMock.get.mock.calls.filter(([url]) => url === "/npa/npa-1")
        .length,
    ).toBeGreaterThanOrEqual(2);

    await act(async () => {
      await user.click(screen.getAllByRole("button", { name: "Отвязать" })[0]);
    });
    expect(apiClientMock.delete).toHaveBeenCalledWith(
      "/npa/npa-1/bindings/b-1",
    );
  });

  it("непересмотренная связь помечена, «Пересмотрено» шлёт review и перечитывает (срез-144)", async () => {
    // Вступила ред. 772н-2026-03, а b-1 сверяли по прошлой: она «не
    // пересмотрена». b-2 уже сверена — у неё кнопки нет.
    const staleDetail = {
      ...npaDetail,
      active_revision_id: "rev-1",
      stale_bindings: 1,
      binding_items: [
        {
          ...npaDetail.binding_items[0],
          reviewed_revision_id: "rev-0",
          reviewed_revision_code: "772н-2025",
          stale: true,
        },
        {
          ...npaDetail.binding_items[1],
          reviewed_revision_id: "rev-1",
          reviewed_revision_code: "772н-2026-03",
          stale: false,
        },
      ],
    };
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({
          data: { items: npaItems, can_manage: false },
        });
      }
      if (url === "/npa/npa-1") {
        return Promise.resolve({ data: staleDetail });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    apiClientMock.post.mockImplementation((url: string) => {
      if (url === "/npa/npa-1/bindings/b-1/review") {
        return Promise.resolve({
          data: { ...staleDetail.binding_items[0], stale: false },
        });
      }
      throw new Error(`Unexpected POST ${url}`);
    });
    const user = userEvent.setup();

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/npa?selected=npa-1"]}>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    expect(await screen.findByTestId("npa-stale-summary")).toHaveTextContent(
      "Требуют пересмотра: 1",
    );
    expect(screen.getAllByTestId("npa-binding-stale")).toHaveLength(1);
    expect(screen.getByTestId("npa-binding-stale")).toHaveTextContent(
      "сверяли по ред. 772н-2025",
    );
    // Кнопка — только у непересмотренной связи, и она не «главная»: бюджет
    // экрана не растёт.
    expect(
      screen.getAllByRole("button", { name: "Пересмотрено" }),
    ).toHaveLength(1);
    expect(uxBudgetDelta(document.body, "NpaPage").unexpected).toEqual([]);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Пересмотрено" }));
    });
    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/npa/npa-1/bindings/b-1/review",
    );
    expect(
      apiClientMock.get.mock.calls.filter(([url]) => url === "/npa/npa-1")
        .length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("неведущиеся связи объяснены словами, а не скрыты (срез-197)", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/npa?selected=npa-1"]}>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    expect(await screen.findByText("772н-2026-03")).toBeInTheDocument();

    const block = await screen.findByTestId("npa-unrecorded");
    // Человек видит, ПОЧЕМУ этих категорий нет, а не делает вывод из их
    // отсутствия.
    expect(block).toHaveTextContent("не записывает");
    expect(block).toHaveTextContent("Риски");
    expect(block).toHaveTextContent("Маршруты");
  });


  it("будущая редакция помечена, а не выглядит действующей (срез-198)", async () => {
    // Владелец платформы заводит редакцию заранее. Без пометки специалист
    // видит её в списке и может начать исполнять новые правила раньше срока.
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/npa?selected=npa-1"]}>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    expect(await screen.findByText("772н-2026-03")).toBeInTheDocument();

    const badges = screen.getAllByTestId("npa-revision-status");
    const states = badges.map((node) => node.getAttribute("data-status"));
    expect(states).toContain("active");
    expect(states).toContain("upcoming");
    expect(
      badges.find((node) => node.getAttribute("data-status") === "upcoming"),
    ).toHaveTextContent("Ещё не вступила в силу");
  });

});
