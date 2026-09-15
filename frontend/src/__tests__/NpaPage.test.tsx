import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
    post: (...args: unknown[]) => apiClientMock.post(...args),
    put: (...args: unknown[]) => apiClientMock.put(...args),
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
    // Срез-201: ящик приходит с сервера и кодом, и словами.
    scope: "registry",
    scope_title: "Общий реестр",
  },
  {
    id: "npa-2",
    code: "2464",
    title: "Постановление № 2464 о порядке обучения",
    edition: "ред. от 01.01.2026",
    valid_from: "2026-01-01",
    valid_to: null,
    clauses: [],
    scope: "registry",
    scope_title: "Общий реестр",
  },
  {
    id: "npa-3",
    code: "29н",
    title: "Приказ № 29н о медосмотрах",
    edition: "ред. от 01.09.2025",
    valid_from: "2025-09-01",
    valid_to: "2026-02-28",
    clauses: [],
    scope: "registry",
    scope_title: "Общий реестр",
  },
];

const npaDetail = {
  act: {
    id: "npa-1",
    code: "772н",
    title: "Приказ Минтруда № 772н об обучении по охране труда",
    edition: "ред. от 01.03.2026",
    scope: "registry",
    scope_title: "Общий реестр",
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
      // Срез-202: текст редакции занесён — её можно сравнивать.
      has_text: true,
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
      has_text: false,
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
    risks:
      "Связь акта с карточкой риска не ведётся: риск — самостоятельная сущность",
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

const npaResponsible = {
  responsible: { user_id: "u-1", name: "Иванов И.И." },
  candidates: [
    { id: "u-1", name: "Иванов И.И." },
    { id: "u-2", name: "Петрова А.С." },
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
    apiClientMock.put.mockReset();
    apiClientMock.delete.mockReset();
    useNpaStore.getState().reset();

    mockRegistry(false);
  });

  const mockRegistry = (
    canManage: boolean,
    items: NpaDto[] = npaItems,
    canCreateOwn = false,
  ) => {
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({
          data: { items, can_manage: canManage, can_create_own: canCreateOwn },
        });
      }
      if (url === "/npa/npa-1") {
        return Promise.resolve({ data: npaDetail });
      }
      // Срез-203: кто ведёт акт в этой организации.
      if (url === "/npa/npa-1/responsible") {
        return Promise.resolve({ data: npaResponsible });
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

    expect(
      (await screen.findAllByTestId("npa-revision-code"))[0],
    ).toHaveTextContent("772н-2026-03");
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
      // Срез-201: ящик называется ЯВНО. Молчание здесь означало бы «решай
      // по правам» — и однажды приказ одной организации ушёл бы в общий
      // реестр для всех.
      scope: "registry",
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

    expect(
      (await screen.findAllByTestId("npa-revision-code"))[0],
    ).toHaveTextContent("772н-2026-03");
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
    expect(
      (await screen.findAllByTestId("npa-revision-code"))[0],
    ).toHaveTextContent("772н-2026-03");

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
    expect(
      (await screen.findAllByTestId("npa-revision-code"))[0],
    ).toHaveTextContent("772н-2026-03");

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
    expect(
      (await screen.findAllByTestId("npa-revision-code"))[0],
    ).toHaveTextContent("772н-2026-03");

    const badges = screen.getAllByTestId("npa-revision-status");
    const states = badges.map((node) => node.getAttribute("data-status"));
    expect(states).toContain("active");
    expect(states).toContain("upcoming");
    expect(
      badges.find((node) => node.getAttribute("data-status") === "upcoming"),
    ).toHaveTextContent("Ещё не вступила в силу");
  });

  it("арендатор заводит СВОЙ акт, и он уходит в свой ящик (срез-201)", async () => {
    // Главное на витрине: кнопок две, и они делают разное. «Добавить акт»
    // пишет в общий реестр для всех арендаторов, «Добавить свой акт» — только
    // себе. Одна кнопка с угадыванием по правам однажды перепутала бы их.
    const user = userEvent.setup();
    mockRegistry(false, npaItems, true);
    apiClientMock.post.mockResolvedValue({
      data: {
        id: "npa-own",
        code: "ПР-1",
        title: "Приказ по организации",
        edition: "ред. 1",
        clauses: [],
        scope: "own",
        scope_title: "Акт организации",
      },
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });

    // Кнопки общего реестра нет: туда ручка ответила бы отказом.
    expect(
      await screen.findByRole("button", { name: "Добавить свой акт" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Добавить акт" }),
    ).not.toBeInTheDocument();

    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: "Добавить свой акт" }),
      );
    });
    // Форма честно говорит, куда попадёт акт.
    expect(screen.getByText("Новый акт организации")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Номер"), "ПР-1");
    await user.type(screen.getByLabelText("Редакция"), "ред. 1");
    await user.type(screen.getByLabelText("Название"), "Приказ по организации");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Добавить" }));
    });

    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/npa",
      expect.objectContaining({ scope: "own", code: "ПР-1" }),
    );
  });

  it("в списке видно, чей акт (срез-201)", async () => {
    // До среза все акты были федеральными, и колонка была бы шумом. Теперь в
    // одном списке лежат общие приказы и свои — а править можно только свои.
    mockRegistry(false, npaItems, true);

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });

    const cells = await screen.findAllByTestId("npa-scope");
    expect(cells.length).toBeGreaterThan(0);
    // Слово приходит с сервера: витрина не переводит код сама.
    expect(cells[0]).toHaveTextContent("Общий реестр");
    expect(cells[0]).toHaveAttribute("data-scope", "registry");
  });

  it("сравнение редакций показывает, что изменилось (срез-202)", async () => {
    const user = userEvent.setup();
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({
          data: { items: npaItems, can_manage: false, can_create_own: false },
        });
      }
      if (url === "/npa/npa-1") return Promise.resolve({ data: npaDetail });
      if (url === "/npa/npa-1/responsible")
        return Promise.resolve({ data: npaResponsible });
      if (url === "/npa/npa-1/revisions/diff") {
        return Promise.resolve({
          data: {
            comparable: true,
            reason: "",
            changes: [
              {
                code: "п. 4",
                change: "modified",
                change_title: "Текст изменён",
                before: "Обучение раз в год",
                after: "Обучение раз в полгода",
              },
            ],
            summary: { added: 0, removed: 0, modified: 1, unchanged: 2 },
            base: { id: "rev-1", revision_code: "772н-2026-03", title: "A" },
            target: {
              id: "rev-next",
              revision_code: "772н-2027-01",
              title: "B",
            },
          },
        });
      }
      if (url === "/documents")
        return Promise.resolve({ data: { items: tenantDocuments } });
      throw new Error(`Unexpected GET ${url}`);
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    await act(async () => {
      await user.click(await screen.findByRole("button", { name: "772н" }));
    });

    await user.selectOptions(screen.getByLabelText("От редакции"), "rev-1");
    await user.selectOptions(screen.getByLabelText("К редакции"), "rev-next");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Сравнить" }));
    });

    const change = await screen.findByTestId("npa-diff-change");
    expect(change).toHaveAttribute("data-change", "modified");
    // Подпись словами приходит с сервера, витрина код не переводит.
    expect(change).toHaveTextContent("Текст изменён");
    expect(change).toHaveTextContent("Обучение раз в полгода");
  });

  it("редакция без текста даёт ПРИЧИНУ, а не пустой список (срез-202)", async () => {
    // ГЛАВНОЕ НА ВИТРИНЕ. Пустой список человек прочитал бы как «закон не
    // менялся» — и не стал бы пересматривать документы.
    const user = userEvent.setup();
    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({
          data: { items: npaItems, can_manage: false, can_create_own: false },
        });
      }
      if (url === "/npa/npa-1") return Promise.resolve({ data: npaDetail });
      if (url === "/npa/npa-1/responsible")
        return Promise.resolve({ data: npaResponsible });
      if (url === "/npa/npa-1/revisions/diff") {
        return Promise.resolve({
          data: {
            comparable: false,
            reason:
              "Текст этой редакции в систему не заносили — сравнивать не с чем",
            changes: [],
            summary: { added: 0, removed: 0, modified: 0, unchanged: 0 },
            base: { id: "rev-1", revision_code: "772н-2026-03", title: "A" },
            target: {
              id: "rev-next",
              revision_code: "772н-2027-01",
              title: "B",
            },
          },
        });
      }
      if (url === "/documents")
        return Promise.resolve({ data: { items: tenantDocuments } });
      throw new Error(`Unexpected GET ${url}`);
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    await act(async () => {
      await user.click(await screen.findByRole("button", { name: "772н" }));
    });
    await user.selectOptions(screen.getByLabelText("От редакции"), "rev-1");
    await user.selectOptions(screen.getByLabelText("К редакции"), "rev-next");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Сравнить" }));
    });

    expect(await screen.findByTestId("npa-diff-unavailable")).toHaveTextContent(
      "не заносили",
    );
    expect(screen.queryByTestId("npa-diff-result")).not.toBeInTheDocument();
  });

  it("редакция без текста помечена прямо в выборе (срез-202)", async () => {
    // Иначе человек выбрал бы её и получил отказ — про это лучше знать заранее.
    const user = userEvent.setup();
    mockRegistry(false);

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    await act(async () => {
      await user.click(await screen.findByRole("button", { name: "772н" }));
    });

    const select = screen.getByLabelText("От редакции");
    expect(select).toHaveTextContent("772н-2027-01 — текста нет");
  });

  it("видно, кто ведёт акт, и его можно сменить (срез-203)", async () => {
    // Разд. 19.1 «owner». До среза задача актуализации доставалась тому, кто
    // нажал кнопку; теперь у акта есть постоянный ответственный, и он виден.
    const user = userEvent.setup();
    mockRegistry(false, npaItems, true);
    apiClientMock.put.mockResolvedValue({
      data: { responsible: { user_id: "u-2", name: "Петрова А.С." } },
    });

    await act(async () => {
      render(
        <MemoryRouter>
          <NpaPage />
        </MemoryRouter>,
      );
    });
    await act(async () => {
      await user.click(await screen.findByRole("button", { name: "772н" }));
    });

    const select = await screen.findByLabelText("Ответственный за акт");
    // Имя приходит с сервера: витрина не собирает его из полей человека.
    expect(select).toHaveTextContent("Иванов И.И.");
    // «Никто не ведёт» — отдельный выбор, а не пустота: это состояние надо
    // заметить и исправить, ему уходят задачи после новой редакции.
    expect(select).toHaveTextContent("Никто не ведёт");

    await act(async () => {
      await user.selectOptions(select, "u-2");
    });

    expect(apiClientMock.put).toHaveBeenCalledWith("/npa/npa-1/responsible", {
      owner_user_id: "u-2",
    });
  });
});
