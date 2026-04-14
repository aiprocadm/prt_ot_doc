import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CommandBar } from "@/components/layout/CommandBar";
import { MobileNavDrawer } from "@/components/layout/MobileNavDrawer";
import { NavMenuProvider } from "@/components/layout/NavMenuProvider";
import { SideNav } from "@/components/layout/SideNav";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

const getBillingSummaryMock = vi.fn();

vi.mock("@/api/billing", () => ({
  getBillingSummary: (...args: unknown[]) => getBillingSummaryMock(...args)
}));

describe("NavMenuProvider", () => {
  it("calls billing summary once for all nav consumers", async () => {
    getBillingSummaryMock.mockResolvedValue({ features: {} });
    useAuthStore.setState({
      user: {
        id: "provider-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
        email: "provider@test.local",
        full_name: "Provider User",
        roles: ["owner"],
        permissions: [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.DOCUMENT_VIEW],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    renderWithRouter(
      <NavMenuProvider>
        <>
          <SideNav />
          <MobileNavDrawer />
          <CommandBar />
        </>
      </NavMenuProvider>
    );

    await waitFor(() => {
      expect(getBillingSummaryMock).toHaveBeenCalledTimes(1);
    });
  });

  it("keeps navigation usable when billing request fails", async () => {
    getBillingSummaryMock.mockRejectedValue(new Error("billing unavailable"));
    useAuthStore.setState({
      user: {
        id: "provider-user-2",
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
        email: "provider2@test.local",
        full_name: "Provider User 2",
        roles: ["owner"],
        permissions: [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.DOCUMENT_VIEW],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    renderWithRouter(
      <NavMenuProvider>
        <SideNav />
      </NavMenuProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Документы" })).toHaveAttribute("href", "/documents");
    });
  });
});
