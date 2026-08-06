import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CalendarPage from "@/pages/calendar/CalendarPage";
import type { CalendarEventsResponseDto } from "@/types/dto/calendar";

const getEventsMock = vi.fn();
const downloadIcsMock = vi.fn();
const downloadBlobMock = vi.fn();
const listSavedViewsMock = vi.fn();
const createSavedViewMock = vi.fn();
const updateSavedViewMock = vi.fn();
const deleteSavedViewMock = vi.fn();

vi.mock("@/api/calendar", () => ({
  calendarApi: {
    getEvents: (...args: unknown[]) => getEventsMock(...args),
    downloadIcs: (...args: unknown[]) => downloadIcsMock(...args),
    listSavedViews: (...args: unknown[]) => listSavedViewsMock(...args),
    createSavedView: (...args: unknown[]) => createSavedViewMock(...args),
    updateSavedView: (...args: unknown[]) => updateSavedViewMock(...args),
    deleteSavedView: (...args: unknown[]) => deleteSavedViewMock(...args),
  },
}));

vi.mock("@/utils/download", () => ({
  downloadBlob: (...args: unknown[]) => downloadBlobMock(...args),
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
    { source_type: "calendar_event", count: 0, overdue_count: 0 },
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
      extra: { exam_type: "periodic" },
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
      extra: {},
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
      extra: {},
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
      extra: { briefing_type: "primary" },
    },
  ],
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
      extra: {},
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
      extra: {},
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
      extra: {},
    },
  ],
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
      title: "Медосмотр: просрочен",
      starts_at: "2026-04-25T08:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: true,
      person_id: "p-1",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: -13,
      sla_band: "overdue",
      extra: {},
    },
    {
      id: "permit:permit-critical",
      source_type: "permit",
      source_id: "permit-critical",
      title: "Допуск: критичный срок",
      starts_at: "2026-05-12T08:00:00Z",
      ends_at: null,
      status: "active",
      is_overdue: false,
      person_id: "p-2",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: 4,
      sla_band: "critical",
      extra: {},
    },
    {
      id: "training_session:ts-warning",
      source_type: "training_session",
      source_id: "ts-warning",
      title: "Обучение: внимание",
      starts_at: "2026-05-20T09:00:00Z",
      ends_at: null,
      status: "scheduled",
      is_overdue: false,
      person_id: "p-1",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: 12,
      sla_band: "warning",
      extra: {},
    },
    {
      id: "ppe_issue:ppe-ok",
      source_type: "ppe_issue",
      source_id: "ppe-ok",
      title: "СИЗ: в норме",
      starts_at: "2026-07-01T08:00:00Z",
      ends_at: null,
      status: "issued",
      is_overdue: false,
      person_id: "p-2",
      site_id: null,
      company_id: null,
      assigned_user_id: null,
      days_to_due: 54,
      sla_band: "ok",
      extra: {},
    },
  ],
};

const renderPage = (initialPath = "/calendar") =>
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <CalendarPage />
    </MemoryRouter>,
  );

describe("CalendarPage", () => {
  beforeEach(() => {
    getEventsMock.mockReset();
    downloadIcsMock.mockReset();
    downloadBlobMock.mockReset();
    listSavedViewsMock.mockReset();
    listSavedViewsMock.mockResolvedValue([]);
    createSavedViewMock.mockReset();
    updateSavedViewMock.mockReset();
    deleteSavedViewMock.mockReset();
  });

  it("loads aggregate from /calendar/events and renders header + counts", async () => {
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Умный календарь" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Всего событий:/)).toBeInTheDocument();
    expect(screen.getAllByText(/Просрочек/).length).toBeGreaterThan(0);
    expect(screen.getByText("Медосмотр: Иванов И.И.")).toBeInTheDocument();
    expect(screen.getByText("СИЗ: Каска")).toBeInTheDocument();
    expect(getEventsMock).toHaveBeenCalledWith({
      source_types: undefined,
      person_id: undefined,
      site_id: undefined,
      include_fact: undefined,
      include_sla: undefined,
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
      items: [sampleResponse.items[0]],
    });

    await user.click(screen.getByRole("button", { name: /Медосмотры/ }));

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: ["medical_exam"],
        person_id: undefined,
        site_id: undefined,
        include_fact: undefined,
        include_sla: undefined,
      });
    });
  });

  it("renders drill-down link for known sources and overdue badge", async () => {
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    const medicalLink = await screen.findByRole("link", {
      name: "Медосмотр: Иванов И.И.",
    });
    expect(medicalLink).toHaveAttribute("href", "/medical?focus=exam-1");

    const overdueRow = medicalLink.closest("tr");
    expect(overdueRow).not.toBeNull();
    expect(
      within(overdueRow as HTMLElement).getByText("Просрочен"),
    ).toBeInTheDocument();
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
      items: [],
    });

    const personInput = screen.getByLabelText("Сотрудник (person_id)");
    await user.type(personInput, "p-1");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: undefined,
        person_id: "p-1",
        site_id: undefined,
        include_fact: undefined,
        include_sla: undefined,
      });
    });
  });

  it("renders empty state when there are no events", async () => {
    getEventsMock.mockResolvedValueOnce({
      ...sampleResponse,
      total: 0,
      overdue_count: 0,
      items: [],
    });

    renderPage();

    expect(
      await screen.findByText("Событий в календаре нет"),
    ).toBeInTheDocument();
  });

  it("renders error state and retries", async () => {
    getEventsMock.mockRejectedValueOnce({
      status: 500,
      message: "boom",
      field_errors: [],
    });

    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();

    getEventsMock.mockResolvedValueOnce(sampleResponse);
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByText("Медосмотр: Иванов И.И."),
    ).toBeInTheDocument();
  });

  it("toggles plan/fact mode and reissues request with include_fact=true", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce(factResponse);

    await user.click(
      screen.getByRole("button", { name: "Сравнить план/факт" }),
    );

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: undefined,
        person_id: undefined,
        site_id: undefined,
        include_fact: true,
        include_sla: undefined,
      });
    });

    expect(
      await screen.findByRole("button", { name: "Скрыть план/факт" }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("columnheader", { name: "План" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Факт" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Отклонение" }),
    ).toBeInTheDocument();
  });

  it("renders variance badges (late / early / on-time) when plan/fact enabled", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    getEventsMock.mockResolvedValueOnce(factResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");
    await user.click(
      screen.getByRole("button", { name: "Сравнить план/факт" }),
    );

    const lateRow = (
      await screen.findByText("Проверка: периодическая")
    ).closest("tr");
    expect(lateRow).not.toBeNull();
    expect(
      within(lateRow as HTMLElement).getByText("+3 дн."),
    ).toBeInTheDocument();

    const earlyRow = screen.getByText("Обучение: внеплановое").closest("tr");
    expect(earlyRow).not.toBeNull();
    expect(
      within(earlyRow as HTMLElement).getByText("-2 дн."),
    ).toBeInTheDocument();

    const onTimeRow = screen.getByText("СИЗ: Респиратор").closest("tr");
    expect(onTimeRow).not.toBeNull();
    // "В срок" appears both in the variance badge and the deadline column;
    // require at least one in this row.
    expect(
      within(onTimeRow as HTMLElement).getAllByText("В срок").length,
    ).toBeGreaterThan(0);

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
    await user.click(
      screen.getByRole("button", { name: "Сравнить план/факт" }),
    );
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
        include_sla: undefined,
      });
    });

    expect(downloadBlobMock).toHaveBeenCalledWith(
      blob,
      expect.stringMatching(/^calendar-.*\.ics$/),
    );
  });

  it("shows ICS error message when download fails", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    downloadIcsMock.mockRejectedValueOnce({
      status: 500,
      message: "ics boom",
      field_errors: [],
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
      include_sla: undefined,
    });
    expect(
      screen.getByRole("button", { name: "Скрыть план/факт" }),
    ).toBeInTheDocument();
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
        include_sla: true,
      });
    });

    expect(
      await screen.findByRole("button", { name: "Скрыть SLA" }),
    ).toBeInTheDocument();
    // slaResponse spans Apr/May/Jul → month-view renders multiple buckets,
    // each with its own SLA columnheader; assert at least one is present.
    expect(
      screen.getAllByRole("columnheader", { name: "SLA" }).length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId("sla-band-filter")).toBeInTheDocument();
  });

  it("renders SLA band badges and days-to-due chips when SLA enabled", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    getEventsMock.mockResolvedValueOnce(slaResponse);

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");
    await user.click(screen.getByRole("button", { name: "Показать SLA" }));

    const overdueRow = (
      await screen.findByText("Медосмотр: просрочен")
    ).closest("tr");
    expect(overdueRow).not.toBeNull();
    const overdueBand = within(overdueRow as HTMLElement).getByText(
      "Просрочено",
    );
    expect(overdueBand).toHaveAttribute("data-sla-band", "overdue");
    expect(
      within(overdueRow as HTMLElement).getByText("Просрочено на 13 дн."),
    ).toBeInTheDocument();

    const criticalRow = screen
      .getByText("Допуск: критичный срок")
      .closest("tr");
    expect(criticalRow).not.toBeNull();
    const criticalBand = within(criticalRow as HTMLElement).getByText(
      "Критично",
    );
    expect(criticalBand).toHaveAttribute("data-sla-band", "critical");
    expect(
      within(criticalRow as HTMLElement).getByText("Осталось 4 дн."),
    ).toBeInTheDocument();

    const warningRow = screen.getByText("Обучение: внимание").closest("tr");
    expect(warningRow).not.toBeNull();
    expect(
      within(warningRow as HTMLElement).getByText("Внимание"),
    ).toHaveAttribute("data-sla-band", "warning");

    const okRow = screen.getByText("СИЗ: в норме").closest("tr");
    expect(okRow).not.toBeNull();
    expect(within(okRow as HTMLElement).getByText("В норме")).toHaveAttribute(
      "data-sla-band",
      "ok",
    );

    const summary = screen.getByTestId("sla-summary");
    expect(summary).toHaveTextContent("просрочено: 1");
    expect(summary).toHaveTextContent("критично: 1");
    expect(summary).toHaveTextContent("внимание: 1");
    expect(summary).toHaveTextContent("в норме: 1");
  });

  it("filters events by selected SLA bands client-side without re-fetching", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    getEventsMock.mockResolvedValueOnce(slaResponse);

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");
    await user.click(screen.getByRole("button", { name: "Показать SLA" }));
    await screen.findByText("Медосмотр: просрочен");

    const callsBefore = getEventsMock.mock.calls.length;

    const filter = screen.getByTestId("sla-band-filter");
    await user.click(within(filter).getByRole("button", { name: /Критично/ }));

    await waitFor(() => {
      expect(
        screen.queryByText("Медосмотр: просрочен"),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText("Допуск: критичный срок")).toBeInTheDocument();
    expect(screen.queryByText("Обучение: внимание")).not.toBeInTheDocument();
    expect(screen.queryByText("СИЗ: в норме")).not.toBeInTheDocument();
    // Filter is purely client-side — no extra fetch.
    expect(getEventsMock.mock.calls.length).toBe(callsBefore);
  });

  it("forwards include_sla=true to ICS download", async () => {
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
        include_sla: true,
      });
    });
  });

  it("hydrates include_sla and sla_bands from URL on mount", async () => {
    getEventsMock.mockResolvedValueOnce(slaResponse);

    renderPage("/calendar?include_sla=1&sla_bands=overdue,critical");

    await screen.findByText("Медосмотр: просрочен");

    expect(getEventsMock).toHaveBeenLastCalledWith({
      source_types: undefined,
      person_id: undefined,
      site_id: undefined,
      include_fact: undefined,
      include_sla: true,
    });
    expect(
      screen.getByRole("button", { name: "Скрыть SLA" }),
    ).toBeInTheDocument();
    // Only "overdue" and "critical" bands shown, others filtered out client-side.
    expect(screen.getByText("Допуск: критичный срок")).toBeInTheDocument();
    expect(screen.queryByText("Обучение: внимание")).not.toBeInTheDocument();
    expect(screen.queryByText("СИЗ: в норме")).not.toBeInTheDocument();
  });

  it("toggles resource load heatmap and shows entities grouped by person", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    // Toggle off → no heatmap.
    expect(
      screen.queryByTestId("resource-load-heatmap"),
    ).not.toBeInTheDocument();

    const callsBefore = getEventsMock.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Показать загрузку" }));

    // Client-side only — no extra fetch.
    expect(getEventsMock.mock.calls.length).toBe(callsBefore);
    expect(
      await screen.findByRole("button", { name: "Скрыть загрузку" }),
    ).toBeInTheDocument();
    const heatmap = screen.getByTestId("resource-load-heatmap");
    expect(heatmap).toBeInTheDocument();

    // sampleResponse has person_id values: p-1 (×3) and p-2 (×1).
    const p1Row = within(heatmap)
      .getAllByRole("row")
      .find((row) => row.getAttribute("data-load-entity") === "p-1");
    expect(p1Row).toBeDefined();
    expect(p1Row).toHaveAttribute("data-load-total", "3");

    const p2Row = within(heatmap)
      .getAllByRole("row")
      .find((row) => row.getAttribute("data-load-entity") === "p-2");
    expect(p2Row).toBeDefined();
    expect(p2Row).toHaveAttribute("data-load-total", "1");
  });

  it("switches resource load dimension between persons and sites", async () => {
    const user = userEvent.setup();
    const responseWithSite: CalendarEventsResponseDto = {
      ...sampleResponse,
      items: [
        { ...sampleResponse.items[0], site_id: "site-A" },
        { ...sampleResponse.items[1], site_id: "site-B" },
        { ...sampleResponse.items[2], site_id: "site-A" },
        { ...sampleResponse.items[3], site_id: null },
      ],
    };
    getEventsMock.mockResolvedValueOnce(responseWithSite);

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");

    await user.click(screen.getByRole("button", { name: "Показать загрузку" }));

    // Default = person → buttons are in the section header, not in the table.
    const section = await screen.findByTestId("resource-load-section");
    expect(
      within(section).getByRole("button", { name: "По людям" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(section).getByRole("button", { name: "По объектам" }),
    ).toHaveAttribute("aria-pressed", "false");

    // Switch to site → 2 rows (site-A=2 events, site-B=1); the briefing with no site_id excluded.
    await user.click(
      within(section).getByRole("button", { name: "По объектам" }),
    );

    await waitFor(() => {
      expect(
        within(section).getByRole("button", { name: "По объектам" }),
      ).toHaveAttribute("aria-pressed", "true");
    });

    const heatmap = await screen.findByTestId("resource-load-heatmap");
    const siteARow = within(heatmap)
      .getAllByRole("row")
      .find((row) => row.getAttribute("data-load-entity") === "site-A");
    expect(siteARow).toBeDefined();
    expect(siteARow).toHaveAttribute("data-load-total", "2");
    const siteBRow = within(heatmap)
      .getAllByRole("row")
      .find((row) => row.getAttribute("data-load-entity") === "site-B");
    expect(siteBRow).toBeDefined();
    expect(siteBRow).toHaveAttribute("data-load-total", "1");
  });

  it("shows empty-state when no events have entity ids in the selected dimension", async () => {
    const user = userEvent.setup();
    const responseNoSites: CalendarEventsResponseDto = {
      ...sampleResponse,
      items: sampleResponse.items.map((item) => ({ ...item, site_id: null })),
    };
    getEventsMock.mockResolvedValueOnce(responseNoSites);

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");

    await user.click(screen.getByRole("button", { name: "Показать загрузку" }));
    const section = await screen.findByTestId("resource-load-section");
    await user.click(
      within(section).getByRole("button", { name: "По объектам" }),
    );

    expect(await screen.findByTestId("resource-load-empty")).toHaveTextContent(
      "site_id",
    );
    expect(
      screen.queryByTestId("resource-load-heatmap"),
    ).not.toBeInTheDocument();
  });

  it("hydrates include_load and load_dim from URL on mount", async () => {
    const responseWithSite: CalendarEventsResponseDto = {
      ...sampleResponse,
      items: [
        { ...sampleResponse.items[0], site_id: "site-A" },
        { ...sampleResponse.items[2], site_id: "site-A" },
      ],
    };
    getEventsMock.mockResolvedValueOnce(responseWithSite);

    renderPage("/calendar?include_load=1&load_dim=site");

    await screen.findByText("Медосмотр: Иванов И.И.");

    expect(
      await screen.findByRole("button", { name: "Скрыть загрузку" }),
    ).toBeInTheDocument();
    const section = await screen.findByTestId("resource-load-section");
    expect(
      within(section).getByRole("button", { name: "По объектам" }),
    ).toHaveAttribute("aria-pressed", "true");
    const heatmap = await screen.findByTestId("resource-load-heatmap");
    const siteARow = within(heatmap)
      .getAllByRole("row")
      .find((row) => row.getAttribute("data-load-entity") === "site-A");
    expect(siteARow).toBeDefined();
    expect(siteARow).toHaveAttribute("data-load-total", "2");
  });

  // --- Saved views (vNext-CAL-01 / Phase 4.1 — saved filters) ---

  it("populates the saved-views dropdown from /calendar/saved-views on mount", async () => {
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    listSavedViewsMock.mockResolvedValueOnce([
      {
        id: "view-overdue",
        name: "Только просрочки",
        payload: {
          view: "week",
          sources: ["medical_exam"],
          person_id: null,
          site_id: null,
          include_fact: false,
          include_sla: true,
          sla_bands: ["overdue"],
          include_load: false,
          load_dim: null,
        },
        created_at: "2026-05-17T10:00:00Z",
        updated_at: "2026-05-17T10:00:00Z",
      },
    ]);

    renderPage();

    await screen.findByText("Медосмотр: Иванов И.И.");

    const select = await screen.findByTestId("saved-views-select");
    // Default option + 1 saved view.
    expect(within(select).getAllByRole("option")).toHaveLength(2);
    expect(
      within(select).getByRole("option", { name: "Только просрочки" }),
    ).toBeInTheDocument();
  });

  it("applies a saved view by reissuing /calendar/events with its filters", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValueOnce(sampleResponse);
    listSavedViewsMock.mockResolvedValueOnce([
      {
        id: "view-medical-sla",
        name: "Медосмотры SLA",
        payload: {
          view: "week",
          sources: ["medical_exam"],
          person_id: "p-1",
          site_id: null,
          include_fact: false,
          include_sla: true,
          sla_bands: ["overdue", "critical"],
          include_load: true,
          load_dim: "site",
        },
        created_at: "2026-05-17T10:00:00Z",
        updated_at: "2026-05-17T10:00:00Z",
      },
    ]);

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");

    getEventsMock.mockResolvedValueOnce({
      ...sampleResponse,
      items: [sampleResponse.items[0]],
    });

    const select = await screen.findByTestId("saved-views-select");
    await user.selectOptions(select, "view-medical-sla");

    await waitFor(() => {
      expect(getEventsMock).toHaveBeenLastCalledWith({
        source_types: ["medical_exam"],
        person_id: "p-1",
        site_id: undefined,
        include_fact: undefined,
        include_sla: true,
      });
    });

    // SLA + load toggles flipped on; "Удалить" button is now visible.
    expect(
      screen.getByRole("button", { name: "Скрыть SLA" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Скрыть загрузку" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("saved-views-delete")).toBeInTheDocument();
  });

  it("saves the current filter state as a new view via prompt", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValue(sampleResponse);
    listSavedViewsMock.mockResolvedValueOnce([]);
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("My filter");
    createSavedViewMock.mockResolvedValueOnce({
      id: "new-view",
      name: "My filter",
      payload: {
        view: "month",
        sources: [],
        person_id: null,
        site_id: null,
        include_fact: false,
        include_sla: false,
        sla_bands: [],
        include_load: false,
        load_dim: null,
      },
      created_at: "2026-05-17T10:00:00Z",
      updated_at: "2026-05-17T10:00:00Z",
    });

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");

    await user.click(screen.getByTestId("saved-views-save"));

    await waitFor(() => {
      expect(createSavedViewMock).toHaveBeenCalledTimes(1);
    });
    expect(createSavedViewMock).toHaveBeenCalledWith({
      name: "My filter",
      payload: expect.objectContaining({
        view: "month",
        sources: [],
        include_fact: false,
        include_sla: false,
        include_load: false,
      }),
    });
    // New view appears in dropdown.
    const select = screen.getByTestId("saved-views-select");
    expect(
      within(select).getByRole("option", { name: "My filter" }),
    ).toBeInTheDocument();

    promptSpy.mockRestore();
  });

  it("shows a conflict error message when name is already taken", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValue(sampleResponse);
    listSavedViewsMock.mockResolvedValueOnce([]);
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("Dup");
    createSavedViewMock.mockRejectedValueOnce({
      status: 409,
      message: "exists",
      field_errors: [],
    });

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");

    await user.click(screen.getByTestId("saved-views-save"));

    expect(await screen.findByTestId("saved-views-error")).toHaveTextContent(
      /Dup/,
    );
    promptSpy.mockRestore();
  });

  it("deletes a saved view after confirm and removes it from the dropdown", async () => {
    const user = userEvent.setup();
    getEventsMock.mockResolvedValue(sampleResponse);
    listSavedViewsMock.mockResolvedValueOnce([
      {
        id: "view-to-delete",
        name: "Удаляемый",
        payload: {
          view: "month",
          sources: [],
          person_id: null,
          site_id: null,
          include_fact: false,
          include_sla: false,
          sla_bands: [],
          include_load: false,
          load_dim: null,
        },
        created_at: "2026-05-17T10:00:00Z",
        updated_at: "2026-05-17T10:00:00Z",
      },
    ]);
    deleteSavedViewMock.mockResolvedValueOnce(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    await screen.findByText("Медосмотр: Иванов И.И.");

    const select = await screen.findByTestId("saved-views-select");
    await user.selectOptions(select, "view-to-delete");
    await screen.findByTestId("saved-views-delete");

    await user.click(screen.getByTestId("saved-views-delete"));

    await waitFor(() => {
      expect(deleteSavedViewMock).toHaveBeenCalledWith("view-to-delete");
    });
    expect(screen.queryByTestId("saved-views-delete")).not.toBeInTheDocument();
    expect(
      within(select).queryByRole("option", { name: "Удаляемый" }),
    ).not.toBeInTheDocument();

    confirmSpy.mockRestore();
  });
});
