import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CalendarPage from "@/pages/calendar/CalendarPage";
import type { CalendarEventsResponseDto } from "@/types/dto/calendar";

const getEventsMock = vi.fn();
const downloadIcsMock = vi.fn();
const downloadBlobMock = vi.fn();

vi.mock("@/api/calendar", () => ({
  calendarApi: {
    getEvents: (...args: unknown[]) => getEventsMock(...args),
    downloadIcs: (...args: unknown[]) => downloadIcsMock(...args)
  }
}));

vi.mock("@/utils/download", () => ({
  downloadBlob: (...args: unknown[]) => downloadBlobMock(...args)
}));

const sampleResponse: CalendarEventsResponseDto = {
  generated_at: "2026-05-07T10:00:00Z",
  range_from: null,
  range_to: null,
  total: 4,
  overdue_count: 2,
  by_source: [
    { source_type: "medical_exam", count: 1, overdue_count: 1 },
    { source_type: "ppe_issue", count: 1, overdue_count: 0 },
    { source_type: "permit", count: 0, overdue_count: 0 },
    { source_type: "training_session", count: 1, overdue_count: 1 },
    { source_type: "inspection", count: 0, overdue_count: 0 },
    { source_type: "compliance_deadline", count: 0, overdue_count: 0 },
    { source_type: "briefing_entry", count: 1, overdue_count: 0 },
    { source_type: "calendar_event", count: 0, overdue_count: 0 }
  ],
  items: [
    {
      id: "medical_exam:exam-1",
      source_type: "medical_exam",
      source_id: "exam-1",
      title: "Медосмотр: Иванов И.И.",
      starts_at: "2026-04-01T08:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: true,
      person_id: "p-1",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      extra: { exam_type: "periodic" }
    },
    {
      id: "ppe_issue:ppe-1",
      source_type: "ppe_issue",
      source_id: "ppe-1",
      title: "СИЗ: Каска",
      starts_at: "2026-05-15T08:00:00Z",
      ends_at: null,
      status: "issued",
      is_overdue: false,
      person_id: "p-2",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      extra: {}
    },
    {
      id: "training_session:ts-1",
      source_type: "training_session",
      source_id: "ts-1",
      title: "Обучение: ОТ базовый курс",
      starts_at: "2026-04-20T09:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: true,
      person_id: "p-1",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      extra: {}
    },
    {
      id: "briefing_entry:brf-1",
      source_type: "briefing_entry",
      source_id: "brf-1",
      title: "Инструктаж: первичный",
      starts_at: "2026-05-08T08:00:00Z",
      ends_at: null,
      status: "signed",
      is_overdue: false,
      person_id: "p-1",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      extra: { briefing_type: "primary" }
    }
  ]
};

const factResponse: CalendarEventsResponseDto = {
  generated_at: "2026-05-07T10:00:00Z",
  range_from: null,
  range_to: null,
  total: 3,
  overdue_count: 0,
  by_source: sampleResponse.by_source,
  items: [
    {
      id: "inspection:insp-late",
      source_type: "inspection",
      source_id: "insp-late",
      title: "Проверка: периодическая",
      starts_at: "2026-04-01T08:00:00Z",
      ends_at: null,
      status: "completed",
      is_overdue: false,
      person_id: null,
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      expected_at: "2026-04-01T08:00:00Z",
      actual_at: "2026-04-04T08:00:00Z",
      variance_days: 3,
      extra: {}
    },
    {
      id: "training_session:ts-early",
      source_type: "training_session",
      source_id: "ts-early",
      title: "Обучение: внеплановое",
      starts_at: "2026-04-10T09:00:00Z",
      ends_at: null,
      status: "completed",
      is_overdue: false,
      person_id: "p-1",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      expected_at: "2026-04-10T09:00:00Z",
      actual_at: "2026-04-08T09:00:00Z",
      variance_days: -2,
      extra: {}
    },
    {
      id: "ppe_issue:ppe-on-time",
      source_type: "ppe_issue",
      source_id: "ppe-on-time",
      title: "СИЗ: Респиратор",
      starts_at: "2026-04-15T08:00:00Z",
      ends_at: null,
      status: "returned",
      is_overdue: false,
      person_id: "p-2",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      expected_at: "2026-04-15T08:00:00Z",
      actual_at: "2026-04-15T08:00:00Z",
      variance_days: 0,
      extra: {}
    }
  ]
};

const slaResponse: CalendarEventsResponseDto = {
  generated_at: "2026-05-08T10:00:00Z",
  range_from: null,
  range_to: null,
  total: 4,
  overdue_count: 1,
  by_source: sampleResponse.by_source,
  items: [
    {
      id: "medical_exam:exam-overdue",
      source_type: "medical_exam",
      source_id: "exam-overdue",
      title: "Медосмотр: Сидоров С.С.",
      starts_at: "2026-04-25T08:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: true,
      person_id: "p-3",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: -13,
      sla_band: "overdue",
      extra: {}
    },
    {
      id: "medical_exam:exam-critical",
      source_type: "medical_exam",
      source_id: "exam-critical",
      title: "Медосмотр: Иванов И.И.",
      starts_at: "2026-05-12T08:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: false,
      person_id: "p-1",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: 4,
      sla_band: "critical",
      extra: {}
    },
    {
      id: "medical_exam:exam-warning",
      source_type: "medical_exam",
      source_id: "exam-warning",
      title: "Медосмотр: Петров П.П.",
      starts_at: "2026-05-28T08:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: false,
      person_id: "p-2",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: 20,
      sla_band: "warning",
      extra: {}
    },
    {
      id: "medical_exam:exam-ok",
      source_type: "medical_exam",
      source_id: "exam-ok",
      title: "Медосмотр: Кузнецов К.К.",
      starts_at: "2026-08-15T08:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: false,
      person_id: "p-4",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: 99,
      sla_band: "ok",
      extra: {}
    }
  ]
};

const renderPage = (initialPath = "/calendar") =>
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <CalendarPage />
    </MemoryRouter>
  );

describe("CalendarPage", () => {
  beforeEach(() => {
    getEventsMock.mockReset();
    downloadIcsMock.mockReset();
    downloadBlobMock.mockReset();
  });

  it("loads aggregate from /calendar/events and renders header + counts", async () => {
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    expect(await screen.findByRole("heading", { name: "Умный календарь" })).toBeInTheDocument();
    expect(screen.getByText(/Всего событий:/)).toBeInTheDocument();
    expect(screen.getAllByText(/Просрочек/).length).toBeGreaterThan(0);
    expect(screen.getByText("Медосмотр: Иванов И.И.")).toBeInTheDocument();
    expect(screen.getByText("СИЗ: Каска")).toBeInTheDocument();
    expect(getEventsMock).toHaveBeenCalledWith({
      source_types: undefined,
      person_id: undefined,
      site_id: undefined,
      include_fact: undefined,
      include_sla: undefined
    });
  });

  it("renders all 5 view toggles and switches view", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValue(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    expect(screen.getByRole("button", { name: "День" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Неделя" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Месяц" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Год" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Список" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Год" }));
    // After year-grouping, all events from 2026 are in one bucket
    expect(screen.getAllByText("Медосмотр: Иванов И.И.")).toHaveLength(1);
  });

  it("filters by source type when a chip is clicked", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce({
      ...sampleResponse,
      total: 1,
      overdue_count: 1,
      items: [sampleResponse.items[0]]
    });

    await user.click(screen.getByRole("button", { name: /Медосмотры/ }));

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: ["medical_exam"],
        person_id: undefined,
        site_id: undefined,
        include_fact: undefined
      });
    });
  });

  it("renders drill-down link for known sources and overdue badge", async () => {
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    const medicalLink = await screen.findByRole("link", { name: "Медосмотр: Иванов И.И." });
    expect(medicalLink).toHaveAttribute("href", "/medical?focus=exam-1");

    const overdueRow = medicalLink.closest("tr");
    expect(overdueRow).not.toBeNull();
    expect(within(overdueRow as HTMLElement).getByText("Просрочен")).toBeInTheDocument();
  });

  it("applies person_id filter when Apply is clicked", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce({
      ...sampleResponse,
      total: 0,
      overdue_count: 0,
      items: []
    });

    const personInput = screen.getByLabelText("Сотрудник (person_id)");
    await user.type(personInput, "p-1");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: undefined,
        person_id: "p-1",
        site_id: undefined,
        include_fact: undefined
      });
    });
  });

  it("renders empty state when there are no events", async () => {
    getEventsMock.mockResolvedValueOnce({
      ...sampleResponse,
      total: 0,
      overdue_count: 0,
      items: []
    });

    renderPage();

    expect(await screen.findByText("Событий в календаре нет")).toBeInTheDocument();
  });

  it("renders error state and retries", async () => {
    getEventsMock.mockRejectedValueOnce({
      status: 500,
      message: "boom",
      field_errors: []
    });

    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();

    getEventsMock.mockResolvedValueOnce(sampleResponse);
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Медосмотр: Иванов И.И.")).toBeInTheDocument();
  });

  it("toggles plan/fact mode and reissues request with include_fact=true", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce(factResponse);

    await user.click(screen.getByRole("button", { name: "Сравнить план/факт" }));

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: undefined,
        person_id: undefined,
        site_id: undefined,
        include_fact: true,
        include_sla: undefined
      });
    });

    expect(
      await screen.findByRole("button", { name: "Скрыть план/факт" })
    ).toBeInTheDocument();

    expect(screen.getByRole("columnheader", { name: "План" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Факт" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Отклонение" })).toBeInTheDocument();
  });

  it("renders variance badges (late / early / on-time) when plan/fact enabled", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    getEventsMock.mockResolvedValueOnce(factResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");
    await user.click(screen.getByRole("button", { name: "Сравнить план/факт" }));

    const lateRow = (await screen.findByText("Проверка: периодическая")).closest("tr");
    expect(lateRow).not.toBeNull();
    expect(within(lateRow as HTMLElement).getByText("+3 дн.")).toBeInTheDocument();

    const earlyRow = screen.getByText("Обучение: внеплановое").closest("tr");
    expect(earlyRow).not.toBeNull();
    expect(within(earlyRow as HTMLElement).getByText("-2 дн.")).toBeInTheDocument();

    const onTimeRow = screen.getByText("СИЗ: Респиратор").closest("tr");
    expect(onTimeRow).not.toBeNull();
    // "В срок" appears both in the variance badge and the deadline column;
    // require at least one in this row.
    expect(within(onTimeRow as HTMLElement).getAllByText("В срок").length).toBeGreaterThan(0);

    const summary = screen.getByTestId("fact-summary");
    expect(summary).toHaveTextContent("Факт зафиксирован: 3");
    expect(summary).toHaveTextContent("опозданий: 1");
    expect(summary).toHaveTextContent("досрочно: 1");
    expect(summary).toHaveTextContent("в срок: 1");
  });

  it("downloads ICS via calendarApi.downloadIcs and forwards filters + include_fact", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce(factResponse);
    await user.click(screen.getByRole("button", { name: "Сравнить план/факт" }));
    await screen.findByRole("button", { name: "Скрыть план/факт" });

    const blob = new Blob(["BEGIN:VCALENDAR"], { type: "text/calendar" });
    downloadIcsMock.mockResolvedValueOnce(blob);

    await user.click(screen.getByRole("button", { name: /Скачать \.ics/ }));

    await waitFor(() => {
      expect(downloadIcsMock).toHaveBeenCalledWith({
        source_types: undefined,
        person_id: undefined,
        site_id: undefined,
        include_fact: true,
        include_sla: undefined
      });
    });

    expect(downloadBlobMock).toHaveBeenCalledWith(blob, expect.stringMatching(/^calendar-.*\.ics$/));
  });

  it("shows ICS error message when download fails", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    downloadIcsMock.mockRejectedValueOnce({
      status: 500,
      message: "ics boom",
      field_errors: []
    });

    await user.click(screen.getByRole("button", { name: /Скачать \.ics/ }));

    expect(await screen.findByText("ics boom")).toBeInTheDocument();
    expect(downloadBlobMock).not.toHaveBeenCalled();
  });

  it("hydrates include_fact from URL on mount", async () => {
    getEventsMock.mockResolvedValueOnce(factResponse);

    renderPage("/calendar?include_fact=1");

    await screen.findByText("Проверка: периодическая");

    expect(getEventsMock).toHaveBeenLastCalledWith({
      source_types: undefined,
      person_id: undefined,
      site_id: undefined,
      include_fact: true,
      include_sla: undefined
    });
    expect(screen.getByRole("button", { name: "Скрыть план/факт" })).toBeInTheDocument();
  });

  it("toggles SLA mode and reissues request with include_sla=true", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce(slaResponse);

    await user.click(screen.getByRole("button", { name: "Показать SLA" }));

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: undefined,
        person_id: undefined,
        site_id: undefined,
        include_fact: undefined,
        include_sla: true
      });
    });

    expect(await screen.findByRole("button", { name: "Скрыть SLA" })).toBeInTheDocument();
    // slaResponse spans April/May/August → month buckets render three tables,
    // each with its own SLA column header.
    expect(screen.getAllByRole("columnheader", { name: "SLA" }).length).toBeGreaterThan(0);
    expect(screen.getByTestId("sla-filter-bar")).toBeInTheDocument();
  });

  it("renders SLA band badges and days-to-due chip when SLA enabled", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    getEventsMock.mockResolvedValueOnce(slaResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");
    await user.click(screen.getByRole("button", { name: "Показать SLA" }));

    const overdueRow = (await screen.findByText("Медосмотр: Сидоров С.С.")).closest("tr");
    expect(overdueRow).not.toBeNull();
    expect(within(overdueRow as HTMLElement).getByTestId("sla-band-overdue")).toBeInTheDocument();
    expect(within(overdueRow as HTMLElement).getByText("Просрочено на 13 дн.")).toBeInTheDocument();

    const criticalRow = screen.getByText("Медосмотр: Иванов И.И.").closest("tr");
    expect(criticalRow).not.toBeNull();
    expect(within(criticalRow as HTMLElement).getByTestId("sla-band-critical")).toBeInTheDocument();
    expect(within(criticalRow as HTMLElement).getByText("Осталось 4 дн.")).toBeInTheDocument();

    const warningRow = screen.getByText("Медосмотр: Петров П.П.").closest("tr");
    expect(warningRow).not.toBeNull();
    expect(within(warningRow as HTMLElement).getByTestId("sla-band-warning")).toBeInTheDocument();
    expect(within(warningRow as HTMLElement).getByText("Осталось 20 дн.")).toBeInTheDocument();

    const okRow = screen.getByText("Медосмотр: Кузнецов К.К.").closest("tr");
    expect(okRow).not.toBeNull();
    expect(within(okRow as HTMLElement).getByTestId("sla-band-ok")).toBeInTheDocument();
    expect(within(okRow as HTMLElement).getByText("Осталось 99 дн.")).toBeInTheDocument();

    const summary = screen.getByTestId("sla-summary");
    expect(summary).toHaveTextContent("просрочено: 1");
    expect(summary).toHaveTextContent("критично: 1");
    expect(summary).toHaveTextContent("внимание: 1");
    expect(summary).toHaveTextContent("в норме: 1");
  });

  it("filters items by selected SLA band chip", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    getEventsMock.mockResolvedValueOnce(slaResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");
    await user.click(screen.getByRole("button", { name: "Показать SLA" }));

    await screen.findByText("Медосмотр: Сидоров С.С.");

    // Initially all 4 SLA rows visible
    expect(screen.getByText("Медосмотр: Кузнецов К.К.")).toBeInTheDocument();

    const slaBar = screen.getByTestId("sla-filter-bar");
    await user.click(within(slaBar).getByRole("button", { name: /Просрочено/ }));

    await waitFor(() => {
      // ok-row hidden once band filter narrows to overdue only
      expect(screen.queryByText("Медосмотр: Кузнецов К.К.")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Медосмотр: Сидоров С.С.")).toBeInTheDocument();
  });

  it("hydrates include_sla and sla_bands from URL on mount", async () => {
    getEventsMock.mockResolvedValueOnce(slaResponse);

    renderPage("/calendar?include_sla=1&sla_bands=overdue,critical");

    await screen.findByText("Медосмотр: Сидоров С.С.");

    expect(getEventsMock).toHaveBeenLastCalledWith({
      source_types: undefined,
      person_id: undefined,
      site_id: undefined,
      include_fact: undefined,
      include_sla: true
    });
    expect(screen.getByRole("button", { name: "Скрыть SLA" })).toBeInTheDocument();
    // Warning and ok rows hidden by the URL-hydrated band filter
    expect(screen.queryByText("Медосмотр: Петров П.П.")).not.toBeInTheDocument();
    expect(screen.queryByText("Медосмотр: Кузнецов К.К.")).not.toBeInTheDocument();
  });

  it("propagates include_sla to ICS download", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce(slaResponse);
    await user.click(screen.getByRole("button", { name: "Показать SLA" }));
    await screen.findByRole("button", { name: "Скрыть SLA" });

    const blob = new Blob(["BEGIN:VCALENDAR"], { type: "text/calendar" });
    downloadIcsMock.mockResolvedValueOnce(blob);

    await user.click(screen.getByRole("button", { name: /Скачать \.ics/ }));

    await waitFor(() => {
      expect(downloadIcsMock).toHaveBeenCalledWith({
        source_types: undefined,
        person_id: undefined,
        site_id: undefined,
        include_fact: undefined,
        include_sla: true
      });
    });
  });
});
