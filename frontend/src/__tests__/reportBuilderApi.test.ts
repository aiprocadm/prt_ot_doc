import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();
const patchMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args)
  }
}));

const downloadBlobMock = vi.fn();
vi.mock("@/utils/download", () => ({ downloadBlob: (...args: unknown[]) => downloadBlobMock(...args) }));

import { reportBuilderApi } from "@/api/reportBuilder";

describe("reportBuilderApi", () => {
  beforeEach(() => {
    getMock.mockReset().mockResolvedValue({ data: {} });
    postMock.mockReset().mockResolvedValue({ data: {} });
    patchMock.mockReset().mockResolvedValue({ data: {} });
    deleteMock.mockReset().mockResolvedValue({ data: {} });
    downloadBlobMock.mockReset();
  });

  it("lists datasets and definitions", async () => {
    await reportBuilderApi.listDatasets();
    expect(getMock).toHaveBeenCalledWith("/report-builder/datasets");
    await reportBuilderApi.listDefinitions();
    expect(getMock).toHaveBeenCalledWith("/report-builder/definitions");
  });

  it("creates, updates, deletes definitions", async () => {
    const payload = { name: "Отчёт", dataset_code: "incidents", config_json: {} };
    await reportBuilderApi.createDefinition(payload);
    expect(postMock).toHaveBeenCalledWith("/report-builder/definitions", payload);
    await reportBuilderApi.updateDefinition("d1", { name: "Новый" });
    expect(patchMock).toHaveBeenCalledWith("/report-builder/definitions/d1", { name: "Новый" });
    await reportBuilderApi.deleteDefinition("d1");
    expect(deleteMock).toHaveBeenCalledWith("/report-builder/definitions/d1");
  });

  it("previews inline config", async () => {
    await reportBuilderApi.preview({ dataset_code: "risks", config_json: { columns: ["hazard"] } });
    expect(postMock).toHaveBeenCalledWith("/report-builder/preview", {
      dataset_code: "risks",
      config_json: { columns: ["hazard"] }
    });
  });

  it("runs a definition and polls the job", async () => {
    await reportBuilderApi.runDefinition("d1", "xlsx");
    expect(postMock).toHaveBeenCalledWith("/report-builder/definitions/d1/run", { format: "xlsx" });
    await reportBuilderApi.getExportJob("j1");
    expect(getMock).toHaveBeenCalledWith("/exports/j1");
  });

  it("downloads the report via the dedicated route", async () => {
    const blob = new Blob(["x"]);
    getMock.mockResolvedValue({ data: blob });
    await reportBuilderApi.downloadReportExport("j1", "report.xlsx");
    expect(getMock).toHaveBeenCalledWith("/report-builder/exports/j1/download", {
      responseType: "blob"
    });
    expect(downloadBlobMock).toHaveBeenCalledWith(blob, "report.xlsx");
  });
});
