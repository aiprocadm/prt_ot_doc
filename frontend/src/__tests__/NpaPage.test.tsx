import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
    post: (...args: unknown[]) => apiClientMock.post(...args),
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
    },
  ],
  bindings: {
    instructions: ["ИОТ-001", "ИОТ-014"],
    trainings: [],
  },
  summary: {
    instructions: 2,
    trainings: 0,
  },
  tasks_to_create: [
    { code: "update-instruction", title: "Обновить инструкции", count: 2 },
  ],
};

describe("NpaPage", () => {
  beforeEach(() => {
    apiClientMock.get.mockReset();
    apiClientMock.post.mockReset();
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
    expect(screen.getByText("ИОТ-001, ИОТ-014")).toBeInTheDocument();
    expect(screen.getByText("Обновить инструкции · 2")).toBeInTheDocument();

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
});
