import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const searchMock = vi.hoisted(() => ({
  fetchSearch: vi.fn(),
  fetchRecentSearches: vi.fn(),
  fetchSavedSearches: vi.fn(),
  createSavedSearch: vi.fn(),
  deleteSavedSearch: vi.fn(),
}));

vi.mock("@/api/search", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fetchSearch: (...args: unknown[]) => searchMock.fetchSearch(...args),
  fetchRecentSearches: () => searchMock.fetchRecentSearches(),
  fetchSavedSearches: () => searchMock.fetchSavedSearches(),
  createSavedSearch: (...args: unknown[]) =>
    searchMock.createSavedSearch(...args),
  deleteSavedSearch: (...args: unknown[]) =>
    searchMock.deleteSavedSearch(...args),
}));

import SearchPage from "@/pages/SearchPage";

const response = {
  q: "инструктаж",
  total: 2,
  facets: {
    type_counts: { document: 1, person: 1 },
    status_counts: { ready: 1 },
  },
  items: [
    {
      kind: "entity" as const,
      entity_type: "document",
      entity_id: "d-1",
      title: "Журнал вводного инструктажа",
      subtitle: "ООО «Ромашка»",
      status: "ready",
      updated_at: "2026-09-01T10:00:00Z",
    },
    {
      kind: "entity" as const,
      entity_type: "person",
      entity_id: "p-1",
      title: "Иванов Иван",
      subtitle: "Слесарь",
      updated_at: "2026-09-02T10:00:00Z",
    },
  ],
  next_cursor: null,
};

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={["/search?q=инструктаж"]}>
        <SearchPage />
      </MemoryRouter>,
    );
  });
};

describe("SearchPage", () => {
  beforeEach(() => {
    searchMock.fetchSearch.mockReset();
    searchMock.fetchRecentSearches.mockReset();
    searchMock.fetchSavedSearches.mockReset();
    searchMock.fetchSearch.mockResolvedValue(response);
    searchMock.fetchRecentSearches.mockResolvedValue([
      { id: "r-1", q: "медосмотр", types: ["document"] },
    ]);
    searchMock.fetchSavedSearches.mockResolvedValue([
      { id: "s-1", name: "Мои документы", q: "документ", types: ["document"] },
    ]);
  });

  it("показывает найденное по запросу из адреса", async () => {
    await renderPage();

    expect(
      await screen.findByText("Журнал вводного инструктажа"),
    ).toBeInTheDocument();
    expect(screen.getByText("Иванов Иван")).toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных", async () => {
    await renderPage();
    await screen.findByText("Журнал вводного инструктажа");

    const budget = uxBudgetDelta(document.body, "SearchPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
