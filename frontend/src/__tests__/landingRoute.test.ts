import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import { getLandingRoute } from "@/router/landing";

vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    getUserWorkspaceConfig: vi.fn().mockRejectedValue(new Error("workspace config unavailable in unit test")),
  },
}));

describe("getLandingRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses dashboard for regular users", async () => {
    const can = (permission: string) => permission === PERMISSIONS.DASHBOARD_VIEW;
    await expect(getLandingRoute(can)).resolves.toBe("/dashboard");
  });

  it("prioritizes attention hub for OT-focused permission set", async () => {
    const can = (permission: string) =>
      [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.TRAINING_VIEW, PERMISSIONS.PPE_VIEW].includes(permission as never);
    await expect(getLandingRoute(can)).resolves.toBe("/workspace/attention");
  });

  it("falls back to client portal when only portal permission exists", async () => {
    const can = (permission: string) => permission === PERMISSIONS.CLIENT_PORTAL_VIEW;
    await expect(getLandingRoute(can)).resolves.toBe("/client-portal/dashboard");
  });

  it("returns access denied route when no permissions available", async () => {
    await expect(getLandingRoute(() => false)).resolves.toBe("/no-access");
  });
});
