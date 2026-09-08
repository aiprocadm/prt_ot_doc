import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const signMock = vi.hoisted(() => ({
  list: vi.fn(),
  refresh: vi.fn(),
  verify: vi.fn(),
}));

vi.mock("@/api/sign", () => ({
  signApi: {
    list: (...args: unknown[]) => signMock.list(...args),
    refresh: (...args: unknown[]) => signMock.refresh(...args),
    verify: (...args: unknown[]) => signMock.verify(...args),
  },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import SignaturesPage from "@/pages/signatures/SignaturesPage";

const requests = [
  {
    id: "aaaaaaaa-1111-2222-3333-444444444444",
    status: "pending",
    provider: "stub",
  },
  {
    id: "bbbbbbbb-5555-6666-7777-888888888888",
    status: "signed",
    provider: "internal",
  },
];

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <SignaturesPage />
      </MemoryRouter>,
    );
  });
  expect(await screen.findByText(/aaaaaaaa/)).toBeInTheDocument();
};

describe("SignaturesPage", () => {
  beforeEach(() => {
    signMock.list.mockReset();
    signMock.refresh.mockReset();
    signMock.verify.mockReset();
    signMock.list.mockResolvedValue(requests);
    signMock.refresh.mockResolvedValue({});
    signMock.verify.mockResolvedValue({});
  });

  it("показывает запросы и называет провайдера у каждого", async () => {
    await renderPage();

    expect(screen.getByText(/provider: stub/)).toBeInTheDocument();
    expect(screen.getByText(/provider: internal/)).toBeInTheDocument();
    // Экран честно предупреждает, что контур не боевой.
    expect(screen.getByText(/non-production/)).toBeInTheDocument();
  });

  it("обновление статуса перечитывает список", async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getAllByRole("button", { name: "Обновить" })[0]);

    expect(signMock.refresh).toHaveBeenCalledWith(requests[0].id);
    // Список перечитан: иначе на экране осталось бы старое состояние.
    expect(signMock.list).toHaveBeenCalledTimes(2);
  });

  it("пустой список — это «запросов нет», а не пустая страница", async () => {
    signMock.list.mockResolvedValue([]);
    await act(async () => {
      render(
        <MemoryRouter>
          <SignaturesPage />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText("Запросы на подпись отсутствуют"),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных", async () => {
    await renderPage();

    const budget = uxBudgetDelta(document.body, "SignaturesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
