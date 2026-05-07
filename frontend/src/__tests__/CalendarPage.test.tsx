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
      include_fact: undefined
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
        include_fact: true
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
        include_fact: true
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
      include_fact: true
    });
    expect(screen.getByRole("button", { name: "Скрыть план/факт" })).toBeInTheDocument();
  });
});
