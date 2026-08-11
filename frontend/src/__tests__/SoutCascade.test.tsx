import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CascadeSection } from "../pages/sout/SoutPage";
import { soutApi } from "../api/sout";

vi.mock("../api/sout", async (orig) => {
  const actual = await orig<typeof import("../api/sout")>();
  return { ...actual, soutApi: { ...actual.soutApi, previewCascade: vi.fn(), applyCascade: vi.fn() } };
});

describe("CascadeSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads preview and applies", async () => {
    (soutApi.previewCascade as ReturnType<typeof vi.fn>).mockResolvedValue({
      assessed_class: "harmful_3_1", can_apply: true,
      medical: [{ exam_kind: "periodic", op: "create", periodicity_months: 12, interval_days: 365,
        target_class: "harmful_3_1", current_class: null, factor_codes: ["4.1"], reason: "r" }],
      ppe_advisory: [],
    });
    (soutApi.applyCascade as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 1, reclassified: 0, conflicts: 0, ppe_advisory_count: 0 });

    render(<CascadeSection workplaceId="w1" />);
    fireEvent.click(screen.getByRole("button", { name: /каскад/i }));
    await waitFor(() => expect(soutApi.previewCascade).toHaveBeenCalledWith("w1"));
    await screen.findByText(/periodic/i);

    fireEvent.click(screen.getByRole("button", { name: /применить/i }));
    await waitFor(() => expect(soutApi.applyCascade).toHaveBeenCalledWith("w1"));
  });

  it("disables apply when plan is empty", async () => {
    (soutApi.previewCascade as ReturnType<typeof vi.fn>).mockResolvedValue({
      assessed_class: "acceptable", can_apply: false, medical: [], ppe_advisory: [] });
    render(<CascadeSection workplaceId="w2" />);
    fireEvent.click(screen.getByRole("button", { name: /каскад/i }));
    await waitFor(() => expect(soutApi.previewCascade).toHaveBeenCalled());
    const applyBtn = await screen.findByRole("button", { name: /применить/i });
    expect(applyBtn).toBeDisabled();
  });
});
