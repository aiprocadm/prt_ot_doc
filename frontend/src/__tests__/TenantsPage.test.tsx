import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TenantsPage from "@/pages/admin/TenantsPage";
import { renderWithRouter } from "@/test-utils/renderWithRouter";
import type { TenantFleetPage } from "@/types/dto/tenants";

const listMock = vi.fn();
const setStatusMock = vi.fn();
const provisionMock = vi.fn();

vi.mock("@/api/tenants", () => ({
  tenantsApi: {
    list: (...args: unknown[]) => listMock(...args),
    setStatus: (...args: unknown[]) => setStatusMock(...args),
    provision: (...args: unknown[]) => provisionMock(...args)
  },
  isNotManagingTenantError: (error: unknown) =>
    Boolean(error && (error as { status?: number }).status === 403)
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({ can: () => true })
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() }
}));

const fleet = (overrides: Partial<TenantFleetPage> = {}): TenantFleetPage => ({
  managing_tenant_slug: "demo",
  total: 2,
  items: [
    {
      tenant: {
        id: "t-1",
        name: "Демо",
        slug: "demo",
        contact_email: "admin@example.com",
        is_active: true,
        kind: "customer"
      },
      quotas: null
    },
    {
      tenant: {
        id: "t-2",
        name: "ООО Ньюко",
        slug: "newco",
        contact_email: "owner@newco.ru",
        is_active: true,
        kind: "customer"
      },
      quotas: {
        tenant_id: "t-2",
        max_parallel_jobs: 4,
        max_doc_generations_per_month: 2500,
        max_storage_mb: 5120,
        monthly_edo_outgoing: 0,
        enforce_billing_gate: false
      }
    }
  ],
  ...overrides
});

describe("TenantsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    setStatusMock.mockReset();
    provisionMock.mockReset();
  });

  it("показывает список тенантов и помечает управляющий", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByText("ООО Ньюко")).toBeInTheDocument();
    expect(screen.getByText("Демо")).toBeInTheDocument();
    expect(screen.getByText("управляющий")).toBeInTheDocument();
  });

  it("показывает лимиты подписки", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByText(/2500 док\/мес/)).toBeInTheDocument();
  });

  it("приостанавливает доступ тенанта", async () => {
    listMock.mockResolvedValue(fleet());
    setStatusMock.mockResolvedValue({ id: "t-2", is_active: false });
    const user = userEvent.setup();

    renderWithRouter(<TenantsPage />);
    const toggle = await screen.findByLabelText("Доступ для ООО Ньюко");
    await user.click(toggle);

    await waitFor(() => expect(setStatusMock).toHaveBeenCalledWith("t-2", false));
  });

  it("не даёт отключить сам управляющий тенант", async () => {
    listMock.mockResolvedValue(fleet());

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByLabelText("Доступ для Демо")).toBeDisabled();
  });

  it("объясняет ситуацию, когда тенант не управляющий", async () => {
    listMock.mockRejectedValue({ status: 403, message: "Forbidden" });

    renderWithRouter(<TenantsPage />);

    expect(
      await screen.findByText("Раздел доступен только управляющему тенанту")
    ).toBeInTheDocument();
  });

  it("показывает пустое состояние, когда тенантов нет", async () => {
    listMock.mockResolvedValue(fleet({ items: [], total: 0 }));

    renderWithRouter(<TenantsPage />);

    expect(await screen.findByText("Тенантов пока нет")).toBeInTheDocument();
  });
});
