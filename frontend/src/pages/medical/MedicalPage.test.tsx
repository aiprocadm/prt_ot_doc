import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import MedicalPage from "./MedicalPage";
import { operationsApi } from "@/api/operations";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

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
  vi.mocked(operationsApi.getMedicalSnapshot).mockResolvedValue({
    exams: [
      {
        id: "e1",
        person_id: "p1",
        exam_type: "periodic",
        exam_date: "2026-01-10",
        conclusion: null,
        valid_until: "2099-01-10",
        created_at: "2026-01-10T00:00:00Z",
        updated_at: "2026-01-10T00:00:00Z",
      },
    ],
    persons: [
      {
        id: "p1",
        first_name: "Иван",
        last_name: "Иванов",
        full_name: "Иванов Иван",
        status: "active",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "p2",
        first_name: "Пётр",
        last_name: "Петров",
        full_name: "Петров Пётр",
        status: "active",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    tasks: [],
  });
  vi.mocked(operationsApi.getPsychiatricSnapshot).mockResolvedValue({
    activityTypes: [
      {
        id: "a1",
        code: "height",
        name: "Работы на высоте",
        interval_days: 1825,
      },
    ],
    contingent: [],
  });
  vi.mocked(operationsApi.seedPsychiatricDefaults).mockResolvedValue({
    count: 9,
  });
  vi.mocked(operationsApi.getMedicalOversightSnapshot).mockResolvedValue({
    summary: {
      by_status: { ok: 1, overdue: 2 },
      total: 5,
      overdue_count: 2,
      suspended_count: 1,
    },
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
  vi.mocked(operationsApi.downloadContingentRegisterPrint).mockResolvedValue(
    undefined,
  );
  vi.mocked(operationsApi.downloadNamedListPrint).mockResolvedValue(undefined);
  vi.mocked(operationsApi.listMedicalReferrals).mockResolvedValue([]);
  vi.mocked(operationsApi.createMedicalReferral).mockResolvedValue({
    id: "r-new",
    person_id: "p1",
    exam_kind: "periodic",
    status: "issued",
    is_overdue: false,
  });
  vi.mocked(operationsApi.transitionMedicalReferral).mockResolvedValue({
    id: "r1",
    person_id: "p1",
    exam_kind: "periodic",
    status: "scheduled",
    is_overdue: false,
  });
  vi.mocked(operationsApi.generateMedicalReferrals).mockResolvedValue({
    count: 4,
  });
  vi.mocked(operationsApi.listMedicalSuspensions).mockResolvedValue([]);
  vi.mocked(operationsApi.liftMedicalSuspension).mockResolvedValue({
    id: "s1",
    person_id: "p1",
    reason: "unfit",
    status: "lifted",
  });
});

describe("MedicalPage psychiatric section", () => {
  it("renders the 342н section with activity types", async () => {
    render(<MedicalPage />);
    await waitFor(() =>
      expect(
        screen.getByText(/Психиатрическое освидетельствование/i),
      ).toBeInTheDocument(),
    );
    expect(await screen.findByText(/Работы на высоте/)).toBeInTheDocument();
  });

  it("calls seedPsychiatricDefaults when the seed button is clicked", async () => {
    vi.mocked(operationsApi.getPsychiatricSnapshot).mockResolvedValue({
      activityTypes: [],
      contingent: [],
    });
    render(<MedicalPage />);
    const btn = await screen.findByRole("button", {
      name: /Загрузить стандартный список 695/i,
    });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(operationsApi.seedPsychiatricDefaults).toHaveBeenCalled(),
    );
  });
});

describe("MedicalPage contingent section", () => {
  it("renders summary stats and the register view by default", async () => {
    render(<MedicalPage />);
    await waitFor(() =>
      expect(screen.getByText("Контингент медосмотров")).toBeInTheDocument(),
    );
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
    await waitFor(() =>
      expect(
        operationsApi.downloadContingentRegisterPrint,
      ).toHaveBeenCalledWith("pdf"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Поимённый список" }));
    fireEvent.click(screen.getByRole("button", { name: "DOCX" }));
    await waitFor(() =>
      expect(operationsApi.downloadNamedListPrint).toHaveBeenCalledWith("docx"),
    );
  });

  it("shows a print error when the renderer is unavailable", async () => {
    vi.mocked(operationsApi.downloadContingentRegisterPrint).mockRejectedValue({
      status: 503,
      message: "PDF converter is unavailable",
    });
    render(<MedicalPage />);
    const pdfBtn = await screen.findByRole("button", { name: "PDF" });
    fireEvent.click(pdfBtn);
    expect(
      await screen.findByText(/PDF converter is unavailable/),
    ).toBeInTheDocument();
  });
});

describe("MedicalPage referrals section", () => {
  it("renders referrals with resolved person names and statuses", async () => {
    vi.mocked(operationsApi.listMedicalReferrals).mockResolvedValue([
      {
        id: "r1",
        person_id: "p1",
        exam_kind: "periodic",
        due_at: "2026-08-01",
        status: "issued",
        medical_org_name: "Клиника",
        result_exam_id: null,
        is_overdue: false,
      },
    ]);
    render(<MedicalPage />);
    await waitFor(() =>
      expect(screen.getByText("Направления на медосмотры")).toBeInTheDocument(),
    );
    expect(await screen.findByText("Выдан")).toBeInTheDocument();
    expect(screen.getAllByText(/Иванов Иван/).length).toBeGreaterThan(0);
    expect(screen.getByText("Клиника")).toBeInTheDocument();
  });

  it("generates referrals by contingent and reloads the list", async () => {
    render(<MedicalPage />);
    const btn = await screen.findByRole("button", {
      name: "Сформировать по контингенту",
    });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(operationsApi.generateMedicalReferrals).toHaveBeenCalled(),
    );
    expect(
      await screen.findByText("Создано направлений: 4"),
    ).toBeInTheDocument();
    expect(
      vi.mocked(operationsApi.listMedicalReferrals).mock.calls.length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("creates a manual referral with the selected person and kind", async () => {
    render(<MedicalPage />);
    const personSelect = await screen.findByLabelText(
      "Сотрудник для направления",
    );
    // Селект статичен, а опции приходят из data.persons (мок API) — без
    // ожидания опции change по value="p2" записал бы "" (гонка).
    await within(personSelect).findByRole("option", { name: "Петров Пётр" });
    fireEvent.change(personSelect, { target: { value: "p2" } });
    fireEvent.change(screen.getByLabelText("Вид осмотра"), {
      target: { value: "psychiatric" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Создать направление" }),
    );
    await waitFor(() =>
      expect(operationsApi.createMedicalReferral).toHaveBeenCalledWith({
        person_id: "p2",
        exam_kind: "psychiatric",
      }),
    );
  });

  it("filters referrals by status server-side", async () => {
    render(<MedicalPage />);
    const filter = await screen.findByLabelText(
      "Фильтр по статусу направления",
    );
    fireEvent.change(filter, { target: { value: "scheduled" } });
    await waitFor(() =>
      expect(operationsApi.listMedicalReferrals).toHaveBeenLastCalledWith({
        status: "scheduled",
      }),
    );
  });

  it("schedules and cancels an issued referral", async () => {
    vi.mocked(operationsApi.listMedicalReferrals).mockResolvedValue([
      {
        id: "r1",
        person_id: "p1",
        exam_kind: "periodic",
        due_at: null,
        status: "issued",
        medical_org_name: null,
        result_exam_id: null,
        is_overdue: false,
      },
    ]);
    render(<MedicalPage />);
    const scheduleBtn = await screen.findByRole("button", {
      name: "Запланировать",
    });
    fireEvent.click(scheduleBtn);
    await waitFor(() =>
      expect(operationsApi.transitionMedicalReferral).toHaveBeenCalledWith(
        "r1",
        { to: "scheduled" },
      ),
    );
    const cancelBtn = await screen.findByRole("button", { name: "Отменить" });
    fireEvent.click(cancelBtn);
    await waitFor(() =>
      expect(operationsApi.transitionMedicalReferral).toHaveBeenCalledWith(
        "r1",
        { to: "cancelled" },
      ),
    );
  });

  it("surfaces a transition error in the alert region", async () => {
    vi.mocked(operationsApi.listMedicalReferrals).mockResolvedValue([
      {
        id: "r1",
        person_id: "p1",
        exam_kind: "periodic",
        due_at: null,
        status: "issued",
        medical_org_name: null,
        result_exam_id: null,
        is_overdue: false,
      },
    ]);
    vi.mocked(operationsApi.transitionMedicalReferral).mockRejectedValue({
      status: 409,
      message: "Invalid transition",
    });
    render(<MedicalPage />);
    const scheduleBtn = await screen.findByRole("button", {
      name: "Запланировать",
    });
    fireEvent.click(scheduleBtn);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid transition",
    );
  });
});

describe("MedicalPage referral completion", () => {
  it("completes a scheduled referral with a selected result exam", async () => {
    vi.mocked(operationsApi.listMedicalReferrals).mockResolvedValue([
      {
        id: "r1",
        person_id: "p1",
        exam_kind: "periodic",
        due_at: null,
        status: "scheduled",
        medical_org_name: null,
        result_exam_id: null,
        is_overdue: false,
      },
    ]);
    render(<MedicalPage />);
    const completeBtn = await screen.findByRole("button", {
      name: "Завершить",
    });
    fireEvent.click(completeBtn);
    const examSelect = await screen.findByLabelText("Осмотр-результат");
    const confirmBtn = screen.getByRole("button", { name: "Подтвердить" });
    expect(confirmBtn).toBeDisabled();
    fireEvent.change(examSelect, { target: { value: "e1" } });
    expect(confirmBtn).not.toBeDisabled();
    fireEvent.click(confirmBtn);
    await waitFor(() =>
      expect(operationsApi.transitionMedicalReferral).toHaveBeenCalledWith(
        "r1",
        { to: "completed", result_exam_id: "e1" },
      ),
    );
  });

  it("shows a hint instead of the picker when the person has no exams", async () => {
    vi.mocked(operationsApi.listMedicalReferrals).mockResolvedValue([
      {
        id: "r2",
        person_id: "p2",
        exam_kind: "periodic",
        due_at: null,
        status: "scheduled",
        medical_org_name: null,
        result_exam_id: null,
        is_overdue: false,
      },
    ]);
    render(<MedicalPage />);
    const completeBtn = await screen.findByRole("button", {
      name: "Завершить",
    });
    fireEvent.click(completeBtn);
    expect(
      await screen.findByText("Сначала зафиксируйте осмотр в реестре выше."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Осмотр-результат")).not.toBeInTheDocument();
  });
});

describe("MedicalPage suspensions section", () => {
  it("renders suspensions with reason labels and source exam", async () => {
    vi.mocked(operationsApi.listMedicalSuspensions).mockResolvedValue([
      {
        id: "s1",
        person_id: "p1",
        reason: "unfit",
        status: "active",
        source_exam_id: "e1",
      },
    ]);
    render(<MedicalPage />);
    await waitFor(() =>
      expect(screen.getByText("Отстранения от работы")).toBeInTheDocument(),
    );
    expect(await screen.findByText("Негоден")).toBeInTheDocument();
    expect(operationsApi.listMedicalSuspensions).toHaveBeenCalledWith({
      status: "active",
    });
  });

  it("lifts an active suspension after confirmation and reloads", async () => {
    vi.mocked(operationsApi.listMedicalSuspensions).mockResolvedValue([
      {
        id: "s1",
        person_id: "p1",
        reason: "unfit",
        status: "active",
        source_exam_id: null,
      },
    ]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MedicalPage />);
    const liftBtn = await screen.findByRole("button", {
      name: "Снять отстранение",
    });
    fireEvent.click(liftBtn);
    await waitFor(() =>
      expect(operationsApi.liftMedicalSuspension).toHaveBeenCalledWith("s1"),
    );
    expect(
      vi.mocked(operationsApi.getMedicalOversightSnapshot).mock.calls.length,
    ).toBeGreaterThanOrEqual(2);
    await waitFor(() =>
      expect(
        vi.mocked(operationsApi.listMedicalSuspensions).mock.calls.length,
      ).toBeGreaterThanOrEqual(2),
    );
    confirmSpy.mockRestore();
  });

  it("surfaces a lift error in the alert region", async () => {
    vi.mocked(operationsApi.listMedicalSuspensions).mockResolvedValue([
      {
        id: "s1",
        person_id: "p1",
        reason: "unfit",
        status: "active",
        source_exam_id: null,
      },
    ]);
    vi.mocked(operationsApi.liftMedicalSuspension).mockRejectedValue({
      status: 403,
      message: "Only admin or owner may lift a medical suspension",
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MedicalPage />);
    const liftBtn = await screen.findByRole("button", {
      name: "Снять отстранение",
    });
    fireEvent.click(liftBtn);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only admin or owner may lift a medical suspension",
    );
    confirmSpy.mockRestore();
  });

  it("does not lift when the confirmation is dismissed", async () => {
    vi.mocked(operationsApi.listMedicalSuspensions).mockResolvedValue([
      {
        id: "s1",
        person_id: "p1",
        reason: "unfit",
        status: "active",
        source_exam_id: null,
      },
    ]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<MedicalPage />);
    const liftBtn = await screen.findByRole("button", {
      name: "Снять отстранение",
    });
    fireEvent.click(liftBtn);
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(operationsApi.liftMedicalSuspension).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("loads all suspensions when the active-only toggle is unchecked", async () => {
    render(<MedicalPage />);
    const toggle = await screen.findByLabelText("Только активные");
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(operationsApi.listMedicalSuspensions).toHaveBeenLastCalledWith(
        undefined,
      ),
    );
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // Мерим НАПОЛНЕННЫЙ экран: направления и отстранения по умолчанию пусты
    // в beforeEach, поэтому даём тесту свои моки — замер пустого экрана
    // это самообман (урок NotificationsPage).
    vi.mocked(operationsApi.listMedicalReferrals).mockResolvedValue([
      {
        id: "r1",
        person_id: "p1",
        exam_kind: "periodic",
        due_at: "2026-08-01",
        status: "issued",
        medical_org_name: "Клиника",
        result_exam_id: null,
        is_overdue: false,
      },
    ]);
    vi.mocked(operationsApi.listMedicalSuspensions).mockResolvedValue([
      {
        id: "s1",
        person_id: "p1",
        reason: "unfit",
        status: "active",
        source_exam_id: "e1",
      },
    ]);
    render(<MedicalPage />);
    // Каждая секция экрана дождалась своих данных из фикстур.
    expect(await screen.findByText(/Работы на высоте/)).toBeInTheDocument();
    expect(await screen.findByText("Электромонтёр")).toBeInTheDocument();
    expect(await screen.findByText("Выдан")).toBeInTheDocument();
    expect(await screen.findByText("Негоден")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "MedicalPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
