import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NavMenuProvider, useNavMenuData } from "@/components/layout/NavMenuProvider";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

const getBillingSummaryMock = vi.fn();

vi.mock("@/api/billing", () => ({
  getBillingSummary: (...args: unknown[]) => getBillingSummaryMock(...args)
}));

const NavMenuConsumerProbe = () => {
  const { visibleGroups, clientPortalOnlyMode } = useNavMenuData();
  return (
    <div>
      <span data-testid="groups-count">{visibleGroups.length}</span>
      <span data-testid="portal-only">{String(clientPortalOnlyMode)}</span>
    </div>
  );
};

describe("NavMenuProvider", () => {
  it("calls billing summary once per provider mount and exposes nav data", async () => {
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
        <NavMenuConsumerProbe />
      </NavMenuProvider>
    );

    await waitFor(() => {
      expect(getBillingSummaryMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByTestId("groups-count")).toHaveTextContent(/[1-9]\d*/);
    expect(screen.getByTestId("portal-only")).toHaveTextContent("false");
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
        <NavMenuConsumerProbe />
      </NavMenuProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("groups-count")).toHaveTextContent(/[1-9]\d*/);
    });
  });
});
