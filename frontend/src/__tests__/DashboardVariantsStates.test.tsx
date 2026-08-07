import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ClientDeliveryDashboardPage from "@/pages/dashboard/ClientDeliveryDashboardPage";
import SafetyDashboardPage from "@/pages/dashboard/SafetyDashboardPage";
import TrainingDashboardPage from "@/pages/dashboard/TrainingDashboardPage";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

describe("Dashboard variants operational states", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("shows empty state on SafetyDashboardPage when API returns empty payload", async () => {
    getMock.mockResolvedValue({ data: {} });

    render(
      <MemoryRouter>
        <SafetyDashboardPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/данные дашборда отсутствуют/i),
    ).toBeInTheDocument();
  });

  it("shows loading state on TrainingDashboardPage while API call is pending", async () => {
    getMock.mockImplementation(() => new Promise(() => undefined));

    render(
      <MemoryRouter>
        <TrainingDashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/загрузка дашборда/i)).toBeInTheDocument();
  });

  it("shows error state on ClientDeliveryDashboardPage when API fails", async () => {
    getMock.mockRejectedValue({
      status: 400,
      message: "dashboard load failed",
    });

    render(
      <MemoryRouter>
        <ClientDeliveryDashboardPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "dashboard load failed",
      );
    });
  });
});
