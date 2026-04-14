import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TopNav } from "@/components/layout/TopNav";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

vi.mock("@/api/navigation", () => ({
  getTopNavKpi: vi.fn().mockResolvedValue({ tasks: 2, alerts: 1 })
}));

vi.mock("@/stores/auth", () => ({
  useAuthStore: (selector?: (state: { user: { email: string; full_name: string }; logout: () => void }) => unknown) => {
    const state = {
      user: { email: "user@test.local", full_name: "Test User" },
      logout: vi.fn()
    };
    return typeof selector === "function" ? selector(state) : state;
  }
}));

vi.mock("@/stores/tenant", () => ({
  useTenantStore: () => ({
    tenant: { id: "t1", name: "Tenant", site: "site-1" },
    tenants: [{ id: "t1", name: "Tenant", site: "site-1" }],
    setTenant: vi.fn()
  })
}));

vi.mock("@/hooks/useTheme", () => ({
  useTheme: () => ["light", vi.fn(), vi.fn()] as const
}));

vi.mock("@/components/GlobalSearch", () => ({
  GlobalSearch: () => <div data-testid="global-search-mock" />
}));

vi.mock("@/components/layout/CommandBar", () => ({
  CommandBar: () => <div data-testid="command-bar-mock" />
}));

vi.mock("@/components/layout/MobileNavDrawer", () => ({
  MobileNavDrawer: () => <div data-testid="mobile-nav-mock" />
}));

describe("TopNav", () => {
  it("renders tasks link to /tasks", async () => {
    renderWithRouter(<TopNav />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /единый реестр задач/i })).toHaveAttribute("href", "/tasks");
    });
  });
});
