import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  fetchSearchMock,
  fetchRecentSearchesMock,
  fetchSavedSearchesMock,
  createSavedSearchMock,
  deleteSavedSearchMock
} = vi.hoisted(() => ({
  fetchSearchMock: vi.fn(),
  fetchRecentSearchesMock: vi.fn(),
  fetchSavedSearchesMock: vi.fn(),
  createSavedSearchMock: vi.fn(),
  deleteSavedSearchMock: vi.fn()
}));

vi.mock("@/api/search", () => ({
  fetchSearch: (...args: unknown[]) => fetchSearchMock(...args),
  fetchRecentSearches: (...args: unknown[]) => fetchRecentSearchesMock(...args),
  fetchSavedSearches: (...args: unknown[]) => fetchSavedSearchesMock(...args),
  createSavedSearch: (...args: unknown[]) => createSavedSearchMock(...args),
  deleteSavedSearch: (...args: unknown[]) => deleteSavedSearchMock(...args)
}));

import SearchPage from "@/pages/SearchPage";

describe("SearchPage states", () => {
  beforeEach(() => {
    fetchSearchMock.mockReset();
    fetchRecentSearchesMock.mockReset();
    fetchSavedSearchesMock.mockReset();
    createSavedSearchMock.mockReset();
    deleteSavedSearchMock.mockReset();
    fetchRecentSearchesMock.mockResolvedValue([]);
    fetchSavedSearchesMock.mockResolvedValue([]);
  });

  it("shows empty state when query has no results", async () => {
    fetchSearchMock.mockResolvedValue({
      items: [],
      facets: {},
      next_cursor: null
    });

    render(
      <MemoryRouter initialEntries={["/search?q=audit&type=documents"]}>
        <SearchPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("shows api error state for failed search", async () => {
    fetchSearchMock.mockRejectedValue({ status: 400, message: "Search backend unavailable" });

    render(
      <MemoryRouter initialEntries={["/search?q=risk&type=documents"]}>
        <SearchPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Search backend unavailable")).toBeInTheDocument());
  });

  it("debounces search input changes before calling api", async () => {
    fetchSearchMock.mockResolvedValue({ items: [], facets: {}, next_cursor: null });

    render(
      <MemoryRouter initialEntries={["/search?q=&type=documents"]}>
        <SearchPage />
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText("Поиск по системе");
    await userEvent.type(input, "audit");

    await waitFor(() => expect(fetchSearchMock).toHaveBeenCalledTimes(1), { timeout: 1200 });
  });

  it("ignores stale responses from older search requests", async () => {
    type SearchPayload = {
      items: Array<{ kind: "entity"; entity_type: string; entity_id: string; title: string }>;
      facets: Record<string, unknown>;
      next_cursor: null;
    };

    const resolvers: {
      first: ((value: SearchPayload) => void) | null;
      second: ((value: SearchPayload) => void) | null;
    } = { first: null, second: null };

    fetchSearchMock
      .mockImplementationOnce(
        () =>
          new Promise<SearchPayload>((resolve) => {
            resolvers.first = resolve;
          })
      )
      .mockImplementationOnce(
        () =>
          new Promise<SearchPayload>((resolve) => {
            resolvers.second = resolve;
          })
      );

    render(
      <MemoryRouter initialEntries={["/search?q=first&type=documents"]}>
        <SearchPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(fetchSearchMock).toHaveBeenCalledTimes(1), { timeout: 1200 });

    const input = screen.getByPlaceholderText("Поиск по системе");
    await userEvent.clear(input);
    await userEvent.type(input, "second");

    await waitFor(() => expect(fetchSearchMock).toHaveBeenCalledTimes(2), { timeout: 1200 });

    resolvers.second!({
      items: [{ kind: "entity", entity_type: "documents", entity_id: "new", title: "Second result" }],
      facets: {},
      next_cursor: null
    });

    expect(await screen.findByText("Second result")).toBeInTheDocument();

    resolvers.first!({
      items: [{ kind: "entity", entity_type: "documents", entity_id: "old", title: "First result" }],
      facets: {},
      next_cursor: null
    });

    await waitFor(() => {
      expect(screen.queryByText("First result")).not.toBeInTheDocument();
    });
  });
});
