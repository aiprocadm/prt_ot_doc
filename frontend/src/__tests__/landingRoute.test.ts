import { describe, expect, it } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import { getLandingRoute } from "@/router/landing";

describe("getLandingRoute", () => {
  it("uses dashboard for regular users", () => {
    const can = (permission: string) => permission === PERMISSIONS.DASHBOARD_VIEW;
    expect(getLandingRoute(can)).toBe("/dashboard");
  });

  it("prioritizes attention hub for OT-focused permission set", () => {
    const can = (permission: string) =>
      [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.TRAINING_VIEW, PERMISSIONS.PPE_VIEW].includes(permission as never);
    expect(getLandingRoute(can)).toBe("/workspace/attention");
  });

  it("falls back to client portal when only portal permission exists", () => {
    const can = (permission: string) => permission === PERMISSIONS.CLIENT_PORTAL_VIEW;
    expect(getLandingRoute(can)).toBe("/client-portal/dashboard");
  });

  it("returns access denied route when no permissions available", () => {
    expect(getLandingRoute(() => false)).toBe("/no-access");
  });
});
