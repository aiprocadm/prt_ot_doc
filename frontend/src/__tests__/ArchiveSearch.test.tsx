import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchSearchMock = vi.fn();

vi.mock("@/api/search", () => ({
  fetchSearch: (...args: unknown[]) => fetchSearchMock(...args),
}));

vi.mock("@/api/files", () => ({
  getDownloadUrl: vi.fn(),
}));

import ArchiveSearch from "@/pages/ArchiveSearch";

const renderPage = (initialRoute = "/archive") =>
  render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/archive" element={<ArchiveSearch />} />
      </Routes>
    </MemoryRouter>
  );

describe("ArchiveSearch", () => {
  beforeEach(() => {
    fetchSearchMock.mockResolvedValue({
      items: [
        {
          kind: "entity",
          entity_type: "documents",
          entity_id: "doc-1",
          title: "Инструкция по ОТ",
          snippet: "результат",
        },
      ],
      facets: { type_counts: { documents: 1 } },
    });
    window.localStorage.clear();
  });

  it("applies filters and updates query params", async () => {
    renderPage();

    await waitFor(() => expect(fetchSearchMock).toHaveBeenCalled());

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Статус"), "ready");

    await waitFor(() => {
      expect(fetchSearchMock).toHaveBeenLastCalledWith(expect.objectContaining({ status: "ready" }));
    });
  });

  it("renders snippet as plain text without HTML injection", async () => {
    const xss = '<img src=x onerror="window.__xss=1">';
    fetchSearchMock.mockResolvedValueOnce({
      items: [
        {
          kind: "entity",
          entity_type: "documents",
          entity_id: "doc-1",
          title: "Test",
          snippet: xss,
        },
      ],
      facets: {},
    });

    const { container } = renderPage();

    await waitFor(() => expect(fetchSearchMock).toHaveBeenCalled());
    expect(await screen.findByText(xss, { exact: false })).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it("saves and applies saved view", async () => {
    renderPage("/archive?status=ready&type=documents");
    await waitFor(() => expect(fetchSearchMock).toHaveBeenCalled());

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Название текущего представления"), "Готовые документы");
    await user.click(screen.getByRole("button", { name: "Сохранить вид" }));

    await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));

    await user.click(screen.getByRole("button", { name: "Готовые документы" }));

    await waitFor(() => {
      expect(fetchSearchMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "ready", types: ["documents"] })
      );
    });
  });
});
