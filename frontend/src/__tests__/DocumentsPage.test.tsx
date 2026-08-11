import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
const listMock = vi.fn();
const downloadMock = vi.fn();
const refreshStatusMock = vi.fn();
const setPageMock = vi.fn();
const setPageSizeMock = vi.fn();
const setFiltersMock = vi.fn();
const getByIdMock = vi.fn();

const storeState = {
  items: [] as unknown,
  item: null,
  filters: {},
  pagination: { page: 1, page_size: 10, total: 1 } as
    | { page: number; page_size: number; total: number }
    | undefined,
  list: listMock,
  setPage: setPageMock,
  setPageSize: setPageSizeMock,
  setFilters: setFiltersMock,
  download: downloadMock,
  refreshStatus: refreshStatusMock,
  generateDocument: vi.fn(),
  getGenerationStatus: vi.fn(),
  getById: getByIdMock,
  loading: false,
  error: null,
};

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
    updated_at: "2024-01-02",
  },
  status: "ready",
  version: "1.0",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  storage: null,
  history: [],
};

vi.mock("@/stores/documents", () => ({
  useDocumentsStore: () => storeState,
}));

vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => ({
    items: [],
    list: vi.fn().mockResolvedValue(undefined),
  }),
}));

import DocumentsPage from "@/pages/documents/DocumentsPage";

describe("DocumentsPage", () => {
  it("loads documents list and opens document card", async () => {
    storeState.items = [mockDocument];
    storeState.pagination = { page: 1, page_size: 10, total: 1 };
    storeState.loading = false;
    storeState.error = null;
    useAuthStore.setState({
      user: {
        id: "user-10",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "user@example.com",
        full_name: "User",
        roles: ["ot_specialist"],
        permissions: [
          PERMISSIONS.DOCUMENT_VIEW,
          PERMISSIONS.DOCUMENT_EXPORT,
          PERMISSIONS.DOCUMENT_SIGN,
          PERMISSIONS.DOCUMENT_CREATE,
        ],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
    render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>,
    );

    expect(listMock).toHaveBeenCalled();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /инструкция по от/i }));

    expect(screen.getByText("Обновить статус")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /инструкция по от/i }),
    ).toBeInTheDocument();
  });

  it("does not crash when documents store contains malformed items or missing pagination", () => {
    storeState.items = null;
    storeState.pagination = undefined;
    storeState.loading = false;
    storeState.error = null;

    useAuthStore.setState({
      user: {
        id: "user-10",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "user@example.com",
        full_name: "User",
        roles: ["ot_specialist"],
        permissions: [PERMISSIONS.DOCUMENT_VIEW, PERMISSIONS.DOCUMENT_CREATE],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter>
        <DocumentsPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Документы" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Документы не найдены")).toBeInTheDocument();
  });
});
