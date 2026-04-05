import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FireInspectionsPage from "@/pages/fire-inspections/FireInspectionsPage";
import FireTrainingPage from "@/pages/fire-training/FireTrainingPage";
import InspectionPrepPackagesPage from "@/pages/inspection-prep/InspectionPrepPackagesPage";

const getInspectionWorkspaceSnapshotMock = vi.fn();
const getFireTrainingSnapshotMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getInspectionWorkspaceSnapshot: (...args: unknown[]) => getInspectionWorkspaceSnapshotMock(...args),
    getFireTrainingSnapshot: (...args: unknown[]) => getFireTrainingSnapshotMock(...args),
  },
}));

describe("Inspection/fire next actions", () => {
  beforeEach(() => {
    getInspectionWorkspaceSnapshotMock.mockReset();
    getFireTrainingSnapshotMock.mockReset();
  });

  it("shows blockers panel on FireInspectionsPage", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue({
      inspections: [
        {
          id: "insp-1",
          authority: "МЧС",
          status: "scheduled",
          scheduled_at: "2020-01-01T00:00:00Z",
          inspection_type: "fire",
          purpose: "Плановая"
        }
      ],
      prescriptions: [{ id: "pres-1", status: "open", inspection_id: "insp-1" }],
      tasks: [{ id: "task-1", status: "open", overdue: true, entity_id: "insp-1" }],
      templates: [],
      packRuns: []
    });

    render(
      <MemoryRouter>
        <FireInspectionsPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/блокеры и дальнейшие действия/i)).toBeInTheDocument();
  });

  it("shows overdue-training next actions on FireTrainingPage", async () => {
    getFireTrainingSnapshotMock.mockResolvedValue({
      templates: [{ id: "tpl-1", title: "Template", status: "active" }],
      journals: [{ id: "jr-1", title: "Journal", status: "active" }],
      overdueEntries: [{ id: "ov-1", briefing_type: "repeat", status: "overdue" }],
      programs: []
    });

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/блокеры и дальнейшие действия/i)).toBeInTheDocument();
    expect(screen.getByText(/просроченных записей инструктажей/i)).toBeInTheDocument();
  });

  it("shows prep-packages blockers panel", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue({
      inspections: [{ id: "insp-1", authority: "Ростехнадзор", status: "open" }],
      prescriptions: [{ id: "pres-1", inspection_id: "insp-1", status: "open" }],
      tasks: [{ id: "task-1", entity_id: "insp-1", status: "open" }],
      templates: [{ id: "tpl-1" }],
      packRuns: []
    });

    render(
      <MemoryRouter>
        <InspectionPrepPackagesPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/блокеры и дальнейшие действия/i)).toBeInTheDocument();
    expect(screen.getByText(/открытых blockers по предписаниям/i)).toBeInTheDocument();
  });
});
