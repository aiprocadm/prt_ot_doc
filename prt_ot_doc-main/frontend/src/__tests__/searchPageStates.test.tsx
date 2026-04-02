import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const {
  fetchSearchMock,
  fetchRecentSearchesMock,
  fetchSavedSearchesMock,
  createSavedSearchMock,
  deleteSavedSearchMock,
} = vi.hoisted(() => ({
  fetchSearchMock: vi.fn(),
  fetchRecentSearchesMock: vi.fn(),
  fetchSavedSearchesMock: vi.fn(),
  createSavedSearchMock: vi.fn(),
  deleteSavedSearchMock: vi.fn(),
}));

vi.mock("@/api/search", () => ({
  fetchSearch: (...args: unknown[]) => fetchSearchMock(...args),
  fetchRecentSearches: (...args: unknown[]) => fetchRecentSearchesMock(...args),
  fetchSavedSearches: (...args: unknown[]) => fetchSavedSearchesMock(...args),
  createSavedSearch: (...args: unknown[]) => createSavedSearchMock(...args),
  deleteSavedSearch: (...args: unknown[]) => deleteSavedSearchMock(...args),
}));

import SearchPage from "@/pages/SearchPage";

describe("SearchPage states", () => {
  it("shows empty state when query has no results", async () => {
    fetchRecentSearchesMock.mockResolvedValue([]);
    fetchSavedSearchesMock.mockResolvedValue([]);
    fetchSearchMock.mockResolvedValue({
      items: [],
      facets: {},
      next_cursor: null,
    });

    render(
      <MemoryRouter initialEntries={["/search?q=audit&type=documents"]}>
        <SearchPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("shows api error state for failed search", async () => {
    fetchRecentSearchesMock.mockResolvedValue([]);
    fetchSavedSearchesMock.mockResolvedValue([]);
    fetchSearchMock.mockRejectedValue({ status: 500, message: "Search backend unavailable" });

    render(
      <MemoryRouter initialEntries={["/search?q=risk&type=documents"]}>
        <SearchPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Search backend unavailable")).toBeInTheDocument());
  });
});
