import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import MedicalPage from "./MedicalPage";
import { operationsApi } from "@/api/operations";

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getMedicalSnapshot: vi.fn(),
    getPsychiatricSnapshot: vi.fn(),
    seedPsychiatricDefaults: vi.fn(),
    getMedicalOversightSnapshot: vi.fn(),
    downloadContingentRegisterPrint: vi.fn(),
    downloadNamedListPrint: vi.fn(),
    listMedicalReferrals: vi.fn(),
    createMedicalReferral: vi.fn(),
    transitionMedicalReferral: vi.fn(),
    generateMedicalReferrals: vi.fn(),
    listMedicalSuspensions: vi.fn(),
    liftMedicalSuspension: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  (operationsApi.getMedicalSnapshot as any).mockResolvedValue({
    exams: [
      {
        id: "e1",
        person_id: "p1",
        exam_type: "periodic",
        exam_date: "2026-01-10",
        conclusion: null,
        valid_until: "2027-01-10",
        created_at: "2026-01-10T00:00:00Z",
        updated_at: "2026-01-10T00:00:00Z",
      },
    ],
    persons: [
      { id: "p1", full_name: "Иванов Иван", status: "active" },
      { id: "p2", full_name: "Петров Пётр", status: "active" },
    ],
    tasks: [],
  });
  (operationsApi.getPsychiatricSnapshot as any).mockResolvedValue({
    activityTypes: [{ id: "a1", code: "height", name: "Работы на высоте", interval_days: 1825 }],
    contingent: [],
  });
  (operationsApi.seedPsychiatricDefaults as any).mockResolvedValue({ count: 9 });
  (operationsApi.getMedicalOversightSnapshot as any).mockResolvedValue({
    summary: { by_status: { ok: 1, overdue: 2 }, total: 5, overdue_count: 2, suspended_count: 1 },
    register: [
      {
        position_id: "pos1",
        position_name: "Электромонтёр",
        factors: [{ code: "4.1", name: "Электрополе" }],
        headcount: 3,
        exam_kinds: ["periodic", "psychiatric"],
        periodicity_months: 12,
      },
    ],
    namedList: [
      {
        person_id: "p1",
        full_name: "Иванов Иван",
        position_name: "Электромонтёр",
        department: "Цех 1",
        factors: [{ code: "4.1", name: "Электрополе" }],
        required_kinds: ["periodic"],
        last_exam_date: "2026-01-10",
        next_due_date: "2027-01-10",
        status: "overdue",
      },
    ],
  });
  (operationsApi.downloadContingentRegisterPrint as any).mockResolvedValue(undefined);
  (operationsApi.downloadNamedListPrint as any).mockResolvedValue(undefined);
  (operationsApi.listMedicalReferrals as any).mockResolvedValue([]);
  (operationsApi.createMedicalReferral as any).mockResolvedValue({ id: "r-new" });
  (operationsApi.transitionMedicalReferral as any).mockResolvedValue({ id: "r1", status: "scheduled" });
  (operationsApi.generateMedicalReferrals as any).mockResolvedValue({ count: 4 });
  (operationsApi.listMedicalSuspensions as any).mockResolvedValue([]);
  (operationsApi.liftMedicalSuspension as any).mockResolvedValue({ id: "s1", status: "lifted" });
});

describe("MedicalPage psychiatric section", () => {
  it("renders the 342н section with activity types", async () => {
    render(<MedicalPage />);
    await waitFor(() =>
      expect(screen.getByText(/Психиатрическое освидетельствование/i)).toBeInTheDocument()
    );
    expect(await screen.findByText(/Работы на высоте/)).toBeInTheDocument();
  });

  it("calls seedPsychiatricDefaults when the seed button is clicked", async () => {
    (operationsApi.getPsychiatricSnapshot as any).mockResolvedValue({ activityTypes: [], contingent: [] });
    render(<MedicalPage />);
    const btn = await screen.findByRole("button", { name: /Загрузить стандартный список 695/i });
    fireEvent.click(btn);
    await waitFor(() => expect(operationsApi.seedPsychiatricDefaults).toHaveBeenCalled());
  });
});

describe("MedicalPage contingent section", () => {
  it("renders summary stats and the register view by default", async () => {
    render(<MedicalPage />);
    await waitFor(() => expect(screen.getByText("Контингент медосмотров")).toBeInTheDocument());
    expect(screen.getByText("Позиций контингента")).toBeInTheDocument();
    expect(await screen.findByText("Электромонтёр")).toBeInTheDocument();
    expect(screen.getByText(/Электрополе/)).toBeInTheDocument();
  });

  it("switches to the named list view", async () => {
    render(<MedicalPage />);
    const btn = await screen.findByRole("button", { name: "Поимённый список" });
    fireEvent.click(btn);
    expect(await screen.findByText("Цех 1")).toBeInTheDocument();
    expect(screen.getByText("Просрочен")).toBeInTheDocument();
  });

  it("downloads the register print form for the active view", async () => {
    render(<MedicalPage />);
    const pdfBtn = await screen.findByRole("button", { name: "PDF" });
    fireEvent.click(pdfBtn);
    await waitFor(() => expect(operationsApi.downloadContingentRegisterPrint).toHaveBeenCalledWith("pdf"));
    fireEvent.click(screen.getByRole("button", { name: "Поимённый список" }));
    fireEvent.click(screen.getByRole("button", { name: "DOCX" }));
    await waitFor(() => expect(operationsApi.downloadNamedListPrint).toHaveBeenCalledWith("docx"));
  });

  it("shows a print error when the renderer is unavailable", async () => {
    (operationsApi.downloadContingentRegisterPrint as any).mockRejectedValue({ status: 503, message: "PDF converter is unavailable" });
    render(<MedicalPage />);
    const pdfBtn = await screen.findByRole("button", { name: "PDF" });
    fireEvent.click(pdfBtn);
    expect(await screen.findByText(/PDF converter is unavailable/)).toBeInTheDocument();
  });
});
