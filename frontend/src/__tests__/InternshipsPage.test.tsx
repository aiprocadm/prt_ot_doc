import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { InternshipDto } from "@/api/internships";
import { PERMISSIONS } from "@/permissions/permissions";
import InternshipsPage from "@/pages/internships/InternshipsPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import { useAuthStore } from "@/stores/auth";

const listMock = vi.fn();
const summaryMock = vi.fn();
const fetchAllPersonsMock = vi.fn();

vi.mock("@/api/internships", async () => {
  const actual =
    await vi.importActual<typeof import("@/api/internships")>(
      "@/api/internships",
    );
  return {
    ...actual,
    internshipsApi: {
      list: (...args: unknown[]) => listMock(...args),
      summary: (...args: unknown[]) => summaryMock(...args),
      create: vi.fn(),
      update: vi.fn(),
    },
  };
});

vi.mock("@/api/personsApi", () => ({
  fetchAllPersons: (...args: unknown[]) => fetchAllPersonsMock(...args),
}));

const setUser = (permissions: string[]) =>
  useAuthStore.setState({
    user: {
      id: "u1",
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
      email: "a@a.io",
      full_name: "Test User",
      roles: ["worker"],
      permissions,
    },
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  } as never);

const internship = (over: Partial<InternshipDto> = {}): InternshipDto => ({
  id: "i1",
  person_id: "p1",
  person_name: "Иванов И. И.",
  mentor_person_id: "p2",
  mentor_name: "Петров П. П.",
  discipline: "road_safety",
  discipline_label: "БДД",
  subject: "Водитель автобуса",
  planned_shifts: 10,
  completed_shifts: 10,
  shifts_remaining: 0,
  completed_short: false,
  started_on: "2026-08-01",
  finished_on: "2026-08-20",
  status: "completed",
  status_label: "Завершена",
  notes: null,
  ...over,
});

const emptySummary = {
  total: 0,
  by_status: { planned: 0, in_progress: 0, completed: 0, cancelled: 0 },
  completed_short: 0,
  active_without_mentor: 0,
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <InternshipsPage />
    </MemoryRouter>,
  );

describe("InternshipsPage — общий экран стажировок (срез-41, Доп. №1 разд. 56.2)", () => {
  beforeEach(() => {
    listMock.mockReset();
    summaryMock.mockReset();
    fetchAllPersonsMock.mockReset();
    summaryMock.mockResolvedValue(emptySummary);
    fetchAllPersonsMock.mockResolvedValue([
      { id: "p1", full_name: "Иванов И. И." },
      { id: "p2", full_name: "Петров П. П." },
    ]);
  });

  it("пустое состояние, когда стажировок нет", async () => {
    listMock.mockResolvedValue([]);
    setUser([PERMISSIONS.TRAINING_VIEW, PERMISSIONS.TRAINING_ASSIGN]);
    renderPage();
    expect(await screen.findByText(/Стажировок нет/i)).toBeInTheDocument();
  });

  it("строки по всем дисциплинам в одном реестре, недобор — отдельной пометкой", async () => {
    // Сущность ядровая: БДД и неразмеченная стажировка лежат в одном списке.
    listMock.mockResolvedValue([
      internship(),
      internship({
        id: "i2",
        person_id: "p2",
        person_name: "Петров П. П.",
        mentor_person_id: null,
        mentor_name: null,
        discipline: null,
        discipline_label: null,
        subject: "Слесарь",
        planned_shifts: 5,
        completed_shifts: 2,
        shifts_remaining: 3,
        completed_short: true,
      }),
    ]);
    setUser([PERMISSIONS.TRAINING_VIEW, PERMISSIONS.TRAINING_ASSIGN]);
    renderPage();

    expect(await screen.findByText("Водитель автобуса")).toBeInTheDocument();
    expect(screen.getByText("Слесарь")).toBeInTheDocument();
    expect(screen.getByText("не размечена")).toBeInTheDocument();
    expect(screen.getByText("не назначен")).toBeInTheDocument();
    // Недобор — только у второй: у первой смен ровно по плану.
    expect(screen.getAllByText("Недобор смен")).toHaveLength(1);
  });

  it("плитки шапки берутся из сводки сервера, а не из строк списка", async () => {
    // Список отдаёт одну строку, а сводка — сорок: на экране должно быть сорок.
    listMock.mockResolvedValue([internship()]);
    summaryMock.mockResolvedValue({
      total: 40,
      by_status: { planned: 3, in_progress: 12, completed: 20, cancelled: 5 },
      completed_short: 4,
      active_without_mentor: 2,
    });
    setUser([PERMISSIONS.TRAINING_VIEW]);
    renderPage();

    await screen.findByText("Водитель автобуса");
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("фильтр по состоянию уходит на сервер параметром status", async () => {
    listMock.mockResolvedValue([internship()]);
    setUser([PERMISSIONS.TRAINING_VIEW]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Водитель автобуса");

    await user.selectOptions(
      screen.getByLabelText("Фильтр по состоянию"),
      "in_progress",
    );
    await waitFor(() =>
      expect(listMock).toHaveBeenLastCalledWith({ status: "in_progress" }),
    );
  });

  it("без training.assign назначить стажировку нельзя", async () => {
    listMock.mockResolvedValue([internship()]);
    setUser([PERMISSIONS.TRAINING_VIEW]);
    renderPage();
    expect(
      await screen.findByRole("button", { name: /Назначить стажировку/i }),
    ).toBeDisabled();
    await screen.findByText("Водитель автобуса");
    expect(screen.queryByRole("button", { name: /Изменить/i })).toBeNull();
  });

  it("граница названа на экране: недобор — факт, допуск решает приказ", async () => {
    listMock.mockResolvedValue([internship()]);
    setUser([PERMISSIONS.TRAINING_VIEW]);
    renderPage();
    await screen.findByText("Водитель автобуса");
    expect(
      screen.getByText(/решает приказ, а не программа/i),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (разд. 59)", async () => {
    listMock.mockResolvedValue([internship(), internship({ id: "i2" })]);
    setUser([PERMISSIONS.TRAINING_VIEW, PERMISSIONS.TRAINING_ASSIGN]);
    renderPage();
    await screen.findAllByText("Водитель автобуса");

    const budget = uxBudgetDelta(document.body, "InternshipsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
