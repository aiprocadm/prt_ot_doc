import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const listMock = vi.fn();
const downloadMock = vi.fn();
const refreshStatusMock = vi.fn();
const setPageMock = vi.fn();
const setPageSizeMock = vi.fn();

const mockDocument = {
  id: "doc-1",
  name: "Инструкция по ОТ",
  type: "instruction",
  company: {
    id: "company-1",
    name: "АО «СеверСтрой»",
    inn: "7701234567",
    status: "active",
    created_at: "2024-01-01",
    updated_at: "2024-01-02"
  },
  status: "ready",
  version: "1.0",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  storage: null,
  history: []
};

vi.mock("@/stores/documents", () => ({
  useDocumentsStore: () => ({
    items: [mockDocument],
    item: null,
    pagination: { page: 1, page_size: 10, total: 1 },
    list: listMock,
    setPage: setPageMock,
    setPageSize: setPageSizeMock,
    download: downloadMock,
    refreshStatus: refreshStatusMock,
    loading: false
  })
}));

import DocumentsPage from "@/pages/documents/DocumentsPage";

describe("DocumentsPage", () => {
  it("loads documents list and opens document card", async () => {
    render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>
    );

    expect(listMock).toHaveBeenCalled();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /инструкция по от/i }));

    expect(screen.getByText("Обновить статус")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /инструкция по от/i })).toBeInTheDocument();
  });
});
