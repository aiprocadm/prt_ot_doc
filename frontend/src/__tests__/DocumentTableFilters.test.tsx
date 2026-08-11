import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DocumentTable } from "@/features/documents/DocumentTable";

const listMock = vi.fn();
const setFiltersMock = vi.fn();
const setPageMock = vi.fn();
const setPageSizeMock = vi.fn();

vi.mock("@/stores/documents", () => ({
  useDocumentsStore: () => ({
    items: [],
    filters: {},
    pagination: { page: 1, page_size: 10, total: 0 },
    list: listMock,
    setPage: setPageMock,
    setPageSize: setPageSizeMock,
    setFilters: setFiltersMock,
    download: vi.fn(),
    refreshStatus: vi.fn(),
    loading: false,
  }),
}));

describe("DocumentTable filters", () => {
  it("updates search and status filters", async () => {
    vi.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<DocumentTable onSelect={vi.fn()} />);

    const search = screen.getByRole("textbox", { name: /поиск по названию/i });
    await user.type(search, "инструкция");
    await act(async () => {
      vi.advanceTimersByTime(450);
    });

    expect(setFiltersMock).toHaveBeenCalledWith({ search: "инструкция" });
    expect(listMock).toHaveBeenCalledWith({ search: "инструкция" });

    const statusSelect = screen.getByLabelText("Статус");
    await user.selectOptions(statusSelect, "draft");

    expect(setFiltersMock).toHaveBeenCalledWith({ status: "draft" });
    expect(listMock).toHaveBeenCalledWith({ status: "draft" });
    vi.useRealTimers();
  });
});
