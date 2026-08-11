import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ApprovalsOutboxPage from "@/pages/approvals/ApprovalsOutboxPage";
import CompaniesPage from "@/pages/companies/CompaniesPage";
import FilesPage from "@/pages/files/FilesPage";

const apiGetMock = vi.fn();

const companiesStoreState = vi.hoisted(() => ({
  items: [] as Array<{ id: string; name: string }>,
  loading: false,
  error: null as { message: string } | null,
  list: vi.fn().mockResolvedValue(undefined),
  getById: vi.fn().mockResolvedValue(null),
}));

const filesStoreState = vi.hoisted(() => ({
  items: [] as Array<{ id: string; name: string }>,
  loading: false,
  error: null as { message: string } | null,
  list: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/layouts/MainLayout", () => ({
  useSidebar: () => ({ setSidebar: vi.fn() }),
}));

vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => ({
    list: companiesStoreState.list,
    getById: companiesStoreState.getById,
    items: companiesStoreState.items,
    loading: companiesStoreState.loading,
    error: companiesStoreState.error,
    pagination: {
      page: 1,
      page_size: 10,
      total: companiesStoreState.items.length,
    },
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    remove: vi.fn(),
  }),
}));

vi.mock("@/stores/files", () => ({
  useFilesStore: () => ({
    list: filesStoreState.list,
    items: filesStoreState.items,
    loading: filesStoreState.loading,
    error: filesStoreState.error,
    pagination: { page: 1, page_size: 10, total: filesStoreState.items.length },
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    remove: vi.fn(),
  }),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiGetMock(...args),
    post: vi.fn(),
  },
}));

describe("Companies/Files/Approvals operational states", () => {
  beforeEach(() => {
    companiesStoreState.items = [];
    companiesStoreState.loading = false;
    companiesStoreState.error = null;
    companiesStoreState.list.mockClear();

    filesStoreState.items = [];
    filesStoreState.loading = false;
    filesStoreState.error = null;
    filesStoreState.list.mockClear();

    apiGetMock.mockReset();
    apiGetMock.mockImplementation((url: string) => {
      if (url === "/admin/outbox")
        return Promise.resolve({ data: { items: [] } });
      if (url === "/admin/outbox/events")
        return Promise.resolve({ data: { items: [] } });
      throw new Error(`Unexpected GET ${url}`);
    });
  });

  it("shows companies empty state", async () => {
    render(
      <MemoryRouter>
        <CompaniesPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/компании не найдены/i)).toBeInTheDocument();
  });

  it("shows files empty state", async () => {
    render(
      <MemoryRouter>
        <FilesPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/файлы не найдены/i)).toBeInTheDocument();
  });

  it("shows approvals outbox empty state", async () => {
    render(
      <MemoryRouter>
        <ApprovalsOutboxPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/исходящие согласования пока отсутствуют/i),
    ).toBeInTheDocument();
  });
});
