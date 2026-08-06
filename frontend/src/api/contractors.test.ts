import { describe, it, expect, vi, beforeEach } from "vitest";

import { apiClient } from "@/api/client";
import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0 } });
  (apiClient.post as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.patch as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.delete as any).mockResolvedValue({ data: null });
});

describe("contractorsApi", () => {
  it("lists the registry with default paging", async () => {
    await contractorsApi.listRegistry();
    expect(apiClient.get).toHaveBeenCalledWith("/contractors/registry", {
      params: { limit: 100, offset: 0 },
    });
  });

  it("scopes employees by contractor_id", async () => {
    await contractorsApi.listEmployees({ contractor_id: "c1" });
    expect(apiClient.get).toHaveBeenCalledWith("/contractors/employees", {
      params: { contractor_id: "c1" },
    });
  });

  it("admits an employee via the admit endpoint", async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { employee_id: "e1", status: "ok", violations: [], warnings: [] },
    });
    const verdict = await contractorsApi.admitEmployee("e1");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/contractors/employees/e1/admit",
    );
    expect(verdict.status).toBe("ok");
  });

  it("archives a document with the document id in the path", async () => {
    await contractorsApi.archiveDocument("d1");
    expect(apiClient.delete).toHaveBeenCalledWith("/contractors/documents/d1");
  });

  it("detects the feature-disabled 404", () => {
    expect(
      isFeatureDisabledError({
        status: 404,
        message: "Contractors feature is not enabled for this tenant",
      }),
    ).toBe(true);
    expect(
      isFeatureDisabledError({ status: 404, message: "Document not found" }),
    ).toBe(false);
    expect(isFeatureDisabledError({ status: 500, message: "boom" })).toBe(
      false,
    );
  });
});
