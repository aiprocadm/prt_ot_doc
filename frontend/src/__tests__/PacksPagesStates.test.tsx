import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PackagePresetsPage from "@/pages/packs/PackagePresetsPage";
import PackageProfilesPage from "@/pages/packs/PackageProfilesPage";
import PacksPage from "@/pages/packs/PacksPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();

type PackRow = {
  id: string;
  name: string;
  preset?: string;
  status?: string;
  updated_at?: string;
  company?: { id: string; name: string };
};

const packsStoreState = vi.hoisted(() => ({
  items: [] as PackRow[],
  loading: false,
  error: null as { status: number; message: string } | null,
  list: vi.fn().mockResolvedValue(undefined),
}));

const companiesStoreState = vi.hoisted(() => ({
  items: [{ id: "company-1", name: "АО Тест" }],
  list: vi.fn(),
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

// Мастер и таблицу НЕ мокаем: UX-бюджет ниже меряет отрисованный экран, и
// пустышки вместо них спрятали бы от замера все кнопки, поля и колонки.
// Мастеру нужен стор компаний — даём управляемый мок.
vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => ({
    items: companiesStoreState.items,
    list: companiesStoreState.list,
  }),
}));

describe("Packs pages operational states", () => {
  beforeEach(() => {
    getMock.mockReset();
    packsStoreState.items = [];
    packsStoreState.loading = false;
    packsStoreState.error = null;
    packsStoreState.list.mockClear();
  });

  it("наполненный экран PacksPage в UX-бюджете (BIZ-60)", async () => {
    // Меряем экран С ДАННЫМИ: шапка со статистикой, мастер на первом шаге и
    // таблица с строками — пустое состояние показало бы бюджет «в норме»
    // ровно потому, что на экране ничего нет.
    packsStoreState.items = [
      {
        id: "pack-1",
        name: "Пакет допуска",
        preset: "site_entry",
        status: "ready",
        updated_at: "2026-08-01T10:00:00Z",
        company: { id: "company-1", name: "АО Тест" },
      },
      {
        id: "pack-2",
        name: "Пакет расследования",
        preset: "incident_response",
        status: "processing",
        updated_at: "2026-08-02T12:00:00Z",
        company: { id: "company-1", name: "АО Тест" },
      },
    ];

    render(
      <MemoryRouter>
        <PacksPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Пакет допуска")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "PacksPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
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
