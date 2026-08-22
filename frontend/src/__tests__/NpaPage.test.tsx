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

const npaItems = [
  {
    id: "npa-1",
    created_at: "2026-01-10T00:00:00Z",
    updated_at: "2026-01-10T00:00:00Z",
    title: "Приказ Минтруда № 772н об обучении по охране труда",
    code: "772н",
    issuer: "Минтруд России",
    status: "active",
    effective_at: "2026-03-01",
    link: "https://npa.example/772n",
  },
  {
    id: "npa-2",
    created_at: "2026-01-11T00:00:00Z",
    updated_at: "2026-01-11T00:00:00Z",
    title: "Постановление № 2464 о порядке обучения",
    code: "2464",
    issuer: "Правительство РФ",
    status: "active",
    effective_at: "2026-01-01",
    link: "https://npa.example/2464",
  },
  {
    id: "npa-3",
    created_at: "2026-01-12T00:00:00Z",
    updated_at: "2026-01-12T00:00:00Z",
    title: "Приказ № 29н о медосмотрах",
    code: "29н",
    issuer: "Минздрав России",
    status: "obsolete",
    effective_at: "2025-09-01",
    link: "https://npa.example/29n",
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

    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/npa") {
        return Promise.resolve({
          data: {
            items: npaItems,
            pagination: { page: 1, page_size: 10, total: npaItems.length },
          },
        });
      }
      if (url === "/npa/npa-1") {
        return Promise.resolve({ data: npaDetail });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
  });

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
    expect(screen.getByText("Постановление № 2464 о порядке обучения")).toBeInTheDocument();

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
});
