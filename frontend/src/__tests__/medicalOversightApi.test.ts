import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { operationsApi } from "@/api/operations";
import { downloadBlob } from "@/utils/download";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
vi.mock("@/utils/download", () => ({ downloadBlob: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("operationsApi medical oversight methods", () => {
  it("getMedicalOversightSnapshot loads summary, register and named list", async () => {
    (apiClient.get as any).mockImplementation((url: string) => {
      if (url === "/medical/summary") {
        return Promise.resolve({
          data: {
            by_status: { ok: 1 },
            total: 3,
            overdue_count: 2,
            suspended_count: 1,
          },
        });
      }
      if (url === "/medical/contingent/register") {
        return Promise.resolve({
          data: {
            items: [
              {
                position_id: "pos1",
                position_name: "Электромонтёр",
                factors: [],
                headcount: 2,
                exam_kinds: ["periodic"],
                periodicity_months: 12,
              },
            ],
            total: 1,
          },
        });
      }
      if (url === "/medical/named-list") {
        return Promise.resolve({
          data: {
            items: [
              {
                person_id: "p1",
                full_name: "Иванов Иван",
                factors: [],
                required_kinds: ["periodic"],
                status: "overdue",
              },
            ],
            total: 1,
          },
        });
      }
      return Promise.reject(new Error(`unexpected url ${url}`));
    });
    const snapshot = await operationsApi.getMedicalOversightSnapshot();
    expect(snapshot.summary.total).toBe(3);
    expect(snapshot.register).toHaveLength(1);
    expect(snapshot.namedList[0].full_name).toBe("Иванов Иван");
  });

  it("downloadContingentRegisterPrint requests a blob and saves it", async () => {
    const blob = new Blob(["x"]);
    (apiClient.get as any).mockResolvedValue({ data: blob });
    await operationsApi.downloadContingentRegisterPrint("pdf");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/medical/contingent/register/print",
      {
        params: { format: "pdf" },
        responseType: "blob",
      },
    );
    expect(downloadBlob).toHaveBeenCalledWith(blob, "contingent-register.pdf");
  });

  it("downloadNamedListPrint requests a blob and saves it", async () => {
    const blob = new Blob(["x"]);
    (apiClient.get as any).mockResolvedValue({ data: blob });
    await operationsApi.downloadNamedListPrint("docx");
    expect(apiClient.get).toHaveBeenCalledWith("/medical/named-list/print", {
      params: { format: "docx" },
      responseType: "blob",
    });
    expect(downloadBlob).toHaveBeenCalledWith(blob, "named-list.docx");
  });

  it("listMedicalReferrals passes the status filter only when set", async () => {
    (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0 } });
    await operationsApi.listMedicalReferrals({ status: "issued" });
    expect(apiClient.get).toHaveBeenCalledWith("/medical/referrals", {
      params: { limit: 100, offset: 0, status: "issued" },
    });
    await operationsApi.listMedicalReferrals();
    expect(apiClient.get).toHaveBeenLastCalledWith("/medical/referrals", {
      params: { limit: 100, offset: 0 },
    });
  });

  it("createMedicalReferral posts the payload", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { id: "r1" } });
    await operationsApi.createMedicalReferral({
      person_id: "p1",
      exam_kind: "periodic",
      due_at: "2026-08-01",
    });
    expect(apiClient.post).toHaveBeenCalledWith("/medical/referrals", {
      person_id: "p1",
      exam_kind: "periodic",
      due_at: "2026-08-01",
    });
  });

  it("transitionMedicalReferral posts to the transition endpoint", async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { id: "r1", status: "completed" },
    });
    await operationsApi.transitionMedicalReferral("r1", {
      to: "completed",
      result_exam_id: "e1",
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/medical/referrals/r1/transition",
      {
        to: "completed",
        result_exam_id: "e1",
      },
    );
  });

  it("generateMedicalReferrals returns the created count", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { count: 4 } });
    const result = await operationsApi.generateMedicalReferrals();
    expect(apiClient.post).toHaveBeenCalledWith(
      "/medical/contingent/generate-referrals",
    );
    expect(result.count).toBe(4);
  });

  it("listMedicalSuspensions passes status=active only when set", async () => {
    (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0 } });
    await operationsApi.listMedicalSuspensions({ status: "active" });
    expect(apiClient.get).toHaveBeenCalledWith("/medical/suspensions", {
      params: { status: "active" },
    });
    await operationsApi.listMedicalSuspensions();
    expect(apiClient.get).toHaveBeenLastCalledWith("/medical/suspensions", {
      params: {},
    });
  });

  it("liftMedicalSuspension posts to the lift endpoint", async () => {
    (apiClient.post as any).mockResolvedValue({
      data: { id: "s1", status: "lifted" },
    });
    await operationsApi.liftMedicalSuspension("s1");
    expect(apiClient.post).toHaveBeenCalledWith("/medical/suspensions/s1/lift");
  });
});
