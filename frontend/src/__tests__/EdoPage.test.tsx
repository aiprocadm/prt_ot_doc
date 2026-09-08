import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const edoMock = vi.hoisted(() => ({ list: vi.fn() }));

vi.mock("@/api/edo", () => ({
  edoApi: { list: (...args: unknown[]) => edoMock.list(...args) },
}));

import EdoPage from "@/pages/edo/EdoPage";

const envelopes = [
  {
    id: "11111111-2222-3333-4444-555555555555",
    status: "sent",
    external_id: "EXT-1",
  },
  {
    id: "66666666-7777-8888-9999-000000000000",
    status: "delivered",
    external_id: null,
  },
];

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <EdoPage />
      </MemoryRouter>,
    );
  });
  expect(await screen.findByText(/11111111/)).toBeInTheDocument();
};

describe("EdoPage", () => {
  beforeEach(() => {
    edoMock.list.mockReset();
    edoMock.list.mockResolvedValue(envelopes);
  });

  it("показывает конверты и честно называет контур небоевым", async () => {
    await renderPage();

    expect(
      screen.getByText(/Provider mode: non-production/),
    ).toBeInTheDocument();
    expect(screen.getByText(/external_id: EXT-1/)).toBeInTheDocument();
    // Пустой внешний идентификатор — прочерк, а не пустое место.
    expect(screen.getByText(/external_id: —/)).toBeInTheDocument();
  });

  it("пустой список — это «сообщений нет», а не пустая страница", async () => {
    edoMock.list.mockResolvedValue([]);
    await act(async () => {
      render(
        <MemoryRouter>
          <EdoPage />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText("ЭДО сообщения отсутствуют"),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных", async () => {
    await renderPage();

    const budget = uxBudgetDelta(document.body, "EdoPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
