import { describe, expect, it, vi, beforeEach } from "vitest";

import { buildToastText, handleApiError } from "@/api/errorHandling";
import type { ApiError } from "@/types/dto/common";

const toastErrorMock = vi.hoisted(() => vi.fn());

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}));

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

const baseError = (
  partial: Partial<ApiError> & Pick<ApiError, "status" | "message">,
): ApiError => ({
  field_errors: [],
  ...partial,
});

describe("buildToastText", () => {
  it("truncates very long primary text", () => {
    const long = "a".repeat(300);
    const err = baseError({ status: 400, message: "x" });
    const out = buildToastText(long, err);
    expect(out.length).toBeLessThanOrEqual(282);
    expect(out.endsWith("…")).toBe(true);
  });

  it("appends correlation ref in DEV when correlation_id is set", () => {
    const err = baseError({
      status: 404,
      message: "n",
      correlation_id: "corr-uuid-123456",
    });
    const out = buildToastText("Not here", err);
    if (import.meta.env.DEV) {
      expect(out).toContain("ref:");
    } else {
      expect(out).toBe("Not here");
    }
  });
});

describe("handleApiError toasts", () => {
  beforeEach(() => {
    toastErrorMock.mockClear();
  });

  it("prefers backend message for 403 when non-empty", () => {
    handleApiError(
      baseError({ status: 403, message: "Worker cannot view this task" }),
    );
    expect(toastErrorMock).toHaveBeenCalledWith("Worker cannot view this task");
  });

  it("uses fallback for 404 when message is empty", () => {
    handleApiError(baseError({ status: 404, message: "   " }));
    expect(toastErrorMock).toHaveBeenCalledWith(
      "Запрошенный ресурс недоступен.",
    );
  });

  it("prefers backend message for 409", () => {
    handleApiError(baseError({ status: 409, message: "Version conflict" }));
    expect(toastErrorMock).toHaveBeenCalledWith("Version conflict");
  });

  it("uses message for 422 when field_errors is empty", () => {
    handleApiError(
      baseError({
        status: 422,
        message: "Payload invalid",
        field_errors: [],
      }),
    );
    expect(toastErrorMock).toHaveBeenCalledWith("Payload invalid");
  });

  it("still joins field_errors for 422 when present", () => {
    handleApiError(
      baseError({
        status: 422,
        message: "ignored when fields",
        field_errors: [{ field: "title", message: "required" }],
      }),
    );
    expect(toastErrorMock).toHaveBeenCalledWith("title: required");
  });
});
