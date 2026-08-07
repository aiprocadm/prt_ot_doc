import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getKpiMock = vi.fn();

vi.mock("@/api/committees", () => ({
  committeesApi: {
    getKpi: (...a: unknown[]) => getKpiMock(...a),
  },
}));

import CommitteeKpiPage from "@/pages/committees/CommitteeKpiPage";

const sampleKpi = {
  committees_total: 2,
  committees_active: 1,
  meetings_planned: 1,
  meetings_held: 3,
  meetings_cancelled: 0,
  decisions_total: 4,
  tasks_total: 5,
  tasks_open: 2,
  tasks_overdue: 1,
  tasks_done: 3,
  held_meetings: 3,
  avg_attendance_pct: 62.5,
  quorum_rate_pct: 66.7,
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <CommitteeKpiPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  getKpiMock.mockReset();
});

describe("CommitteeKpiPage", () => {
  it("renders metric groups and values from the DTO", async () => {
    getKpiMock.mockResolvedValue(sampleKpi);

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("KPI комитетов")).toBeInTheDocument(),
    );
    // Grouped sections with RU labels.
    expect(screen.getByText("Заседания")).toBeInTheDocument();
    expect(screen.getByText("Задачи")).toBeInTheDocument();
    expect(screen.getByText("Явка и кворум")).toBeInTheDocument();
    // A concrete count and a formatted percentage.
    expect(screen.getByText("Проведено")).toBeInTheDocument();
    expect(screen.getByText("62.5 %")).toBeInTheDocument();
    expect(screen.getByText("66.7 %")).toBeInTheDocument();
  });

  it("shows a friendly EmptyState when the module flag is off (404)", async () => {
    getKpiMock.mockRejectedValue({ status: 404, message: "not found" });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Модуль комитетов отключён")).toBeInTheDocument(),
    );
  });

  it("shows an ErrorState on a non-404 failure", async () => {
    getKpiMock.mockRejectedValue({ status: 500, message: "boom" });

    renderPage();

    // Мок вызывается синхронно в первом эффекте, ДО setError/setLoading(false),
    // а до этого страница — LoadingScreen; ждём сам ErrorState (role=alert).
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    // Title still renders; the KPI groups do not.
    expect(screen.getByText("KPI комитетов")).toBeInTheDocument();
    expect(screen.queryByText("Явка и кворум")).not.toBeInTheDocument();
  });
});
