import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SoutPage from "@/pages/sout/SoutPage";

const listMock = vi.fn();
const getReportMock = vi.fn();
const downloadSummaryMock = vi.fn();
const downloadCardMock = vi.fn();

vi.mock("@/api/sout", () => ({
  soutApi: {
    list: (...args: unknown[]) => listMock(...args),
    getReport: (...args: unknown[]) => getReportMock(...args),
    downloadSummary: (...args: unknown[]) => downloadSummaryMock(...args),
    downloadCard: (...args: unknown[]) => downloadCardMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const campaign = {
  id: "c1",
  name: "Кампания 2026",
  status: "draft",
  report_number: "Р-1",
  created_at: "2026-01-01",
  updated_at: "2026-01-02",
};

const workplace = {
  id: "w1",
  campaign_id: "c1",
  workplace_code: "РМ-01",
  position_name: "Сварщик",
  is_reassessment_due: false,
};

describe("SoutPage print download error handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listMock.mockResolvedValue({ items: [campaign], total: 1, limit: 100, offset: 0 });
    getReportMock.mockResolvedValue({
      campaign,
      workplaces: [{ workplace, factors: [], guarantees: [] }],
    });
  });

  it("shows 503 toast when PDF summary conversion is unavailable", async () => {
    const { toast } = await import("sonner");
    downloadSummaryMock.mockRejectedValue({ response: { status: 503 } });

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SoutPage />
      </MemoryRouter>,
    );

    // Select the campaign so ReportPanel mounts.
    await user.click(await screen.findByText("Кампания 2026"));

    // Wait for the report (workplace row) to render.
    await screen.findByText(/РМ-01/);

    await user.click(screen.getByRole("button", { name: "Сводная PDF" }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("PDF-конвертер недоступен, скачайте DOCX");
    });
  });
});
