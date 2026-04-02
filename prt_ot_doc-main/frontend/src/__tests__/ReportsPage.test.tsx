import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import ReportsPage from "@/pages/reports/ReportsPage";
import { useAuthStore } from "@/stores/auth";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args)
  }
}));

describe("ReportsPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    getMock.mockResolvedValue({
      data: {
        risks_high: 1,
        trainings_overdue: 2,
        ppe_issues_month: 3,
        incidents_open: 4,
        prescriptions_overdue: 5
      }
    });
    postMock.mockResolvedValue({ data: { id: "export-1", status: "queued" } });

    useAuthStore.setState({
      user: {
        id: "reports-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "reports@example.com",
        full_name: "Reports User",
        roles: ["project_manager"],
        permissions: [PERMISSIONS.REPORTS_VIEW, PERMISSIONS.DOCUMENT_EXPORT],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });
  });

  it("runs export when user has export permission", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith("/reports/kpi", expect.anything());
    });

    const exportButton = screen.getByRole("button", { name: "XLSX" });
    expect(exportButton).toBeEnabled();

    await user.click(exportButton);

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/exports",
        expect.objectContaining({ export_type: "reports:xlsx" }),
        expect.anything()
      );
    });
  });

  it("shows disabled export actions without reports/export permissions", async () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? {
            ...state.user,
            roles: ["worker"],
            permissions: []
          }
        : null
    }));

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    const xlsxButton = await screen.findByRole("button", { name: "XLSX" });
    const pdfButton = screen.getByRole("button", { name: "PDF" });
    expect(xlsxButton).toBeDisabled();
    expect(pdfButton).toBeDisabled();

    await user.click(xlsxButton);
    expect(postMock).not.toHaveBeenCalled();
  });
});
