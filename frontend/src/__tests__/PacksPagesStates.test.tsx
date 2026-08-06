import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PackagePresetsPage from "@/pages/packs/PackagePresetsPage";
import PackageProfilesPage from "@/pages/packs/PackageProfilesPage";
import PacksPage from "@/pages/packs/PacksPage";

const getMock = vi.fn();

const packsStoreState = vi.hoisted(() => ({
  items: [] as Array<{ id: string; name: string }>,
  loading: false,
  error: null as { status: number; message: string } | null,
  list: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
  },
}));

vi.mock("@/stores/packs", () => ({
  usePacksStore: () => ({
    list: packsStoreState.list,
    items: packsStoreState.items,
    loading: packsStoreState.loading,
    error: packsStoreState.error,
    pagination: { page: 1, page_size: 10, total: packsStoreState.items.length },
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    create: vi.fn(),
    setFilters: vi.fn(),
    getById: vi.fn(),
    reset: vi.fn(),
    item: null,
    filters: {},
  }),
}));

vi.mock("@/features/packs/PackWizard", () => ({
  PackWizard: () => <div data-testid="pack-wizard" />,
}));

vi.mock("@/features/packs/PackTable", () => ({
  PackTable: () => <div data-testid="pack-table" />,
}));

describe("Packs pages operational states", () => {
  beforeEach(() => {
    getMock.mockReset();
    packsStoreState.items = [];
    packsStoreState.loading = false;
    packsStoreState.error = null;
    packsStoreState.list.mockClear();
  });

  it("shows empty state on PacksPage", async () => {
    render(
      <MemoryRouter>
        <PacksPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/пакеты не найдены/i)).toBeInTheDocument();
  });

  it("shows empty state on PackagePresetsPage when API returns no data", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/package-presets") return Promise.resolve({ data: [] });
      if (url === "/package-profiles") return Promise.resolve({ data: [] });
      throw new Error(`Unexpected GET ${url}`);
    });

    render(
      <MemoryRouter>
        <PackagePresetsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/пресеты пакетов отсутствуют/i),
    ).toBeInTheDocument();
  });

  it("shows error state on PackageProfilesPage when API fails", async () => {
    getMock.mockRejectedValue({ status: 400, message: "profiles load failed" });

    render(
      <MemoryRouter>
        <PackageProfilesPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "profiles load failed",
      );
    });
  });
});
