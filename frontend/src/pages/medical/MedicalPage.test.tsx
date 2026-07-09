import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import MedicalPage from "./MedicalPage";
import { operationsApi } from "@/api/operations";

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getMedicalSnapshot: vi.fn(),
    getPsychiatricSnapshot: vi.fn(),
    seedPsychiatricDefaults: vi.fn(),
  },
}));

beforeEach(() => {
  (operationsApi.getMedicalSnapshot as any).mockResolvedValue({ exams: [], persons: [], tasks: [] });
  (operationsApi.getPsychiatricSnapshot as any).mockResolvedValue({
    activityTypes: [{ id: "a1", code: "height", name: "Работы на высоте", interval_days: 1825 }],
    contingent: [],
  });
  (operationsApi.seedPsychiatricDefaults as any).mockResolvedValue({ count: 9 });
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
