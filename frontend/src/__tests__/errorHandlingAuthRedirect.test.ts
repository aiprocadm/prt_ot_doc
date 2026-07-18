import { describe, expect, it, vi } from "vitest";

import { handleApiError } from "@/api/errorHandling";

const requestAuthRedirectMock = vi.hoisted(() => vi.fn());
const tokenClearMock = vi.hoisted(() => vi.fn());

vi.mock("@/router/authRedirect", () => ({
  requestAuthRedirect: (...args: unknown[]) => requestAuthRedirectMock(...args),
}));

vi.mock("@/api/tokenStorage", () => ({
  tokenStorage: {
    clear: (...args: unknown[]) => tokenClearMock(...args),
  },
}));

describe("handleApiError unauthorized flow", () => {
  it("uses centralized auth redirect helper for 401", () => {
    handleApiError({ status: 401, message: "Unauthorized" });
    expect(tokenClearMock).toHaveBeenCalledTimes(1);
    expect(requestAuthRedirectMock).toHaveBeenCalledWith("unauthorized");
  });
});
