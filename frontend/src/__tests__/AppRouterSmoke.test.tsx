import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "@/App";
import { useTenantStore } from "@/stores/tenant";

const mockInitialize = vi.fn().mockResolvedValue(undefined);
const mockAuthState = {
  initialize: mockInitialize,
  isAuthenticated: true,
  initialized: true,
  user: { email: "demo@example.com", full_name: "Demo User" },
  logout: vi.fn(),
};

vi.mock("@/stores/auth", () => ({
  useAuthStore: (selector?: (state: typeof mockAuthState) => unknown) =>
    typeof selector === "function" ? selector(mockAuthState) : mockAuthState,
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({ can: () => true }),
}));

describe("AppRouter", () => {
  it("renders the main dashboard route", async () => {
    window.history.pushState({}, "", "/dashboard");
    useTenantStore.getState().setTenant(useTenantStore.getState().tenants[0]);
    render(<App />);

    expect(
      await screen.findByRole(
        "heading",
        { name: "Единый рабочий стол ОТ/ПБ" },
        { timeout: 7000 },
      ),
    ).toBeInTheDocument();
  });
});
