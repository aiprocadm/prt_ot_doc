import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  Attendance,
  Committee,
  MemberDetail,
  Meeting,
  Protocol,
  ProtocolJournalItem,
} from "@/api/committees";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  listMeetings: vi.fn(),
  listMembers: vi.fn(),
  getAttendance: vi.fn(),
  putAttendance: vi.fn(),
  getProtocol: vi.fn(),
  listProtocols: vi.fn(),
  createCommittee: vi.fn(),
  addMember: vi.fn(),
  removeMember: vi.fn(),
  createMeeting: vi.fn(),
  createDecision: vi.fn(),
  createTask: vi.fn(),
  updateTask: vi.fn(),
  holdMeeting: vi.fn(),
  castVote: vi.fn(),
  getVotes: vi.fn(),
}));

vi.mock("@/api/committees", () => ({ committeesApi: api }));

import CommitteesPage from "@/pages/committees/CommitteesPage";

const COMMITTEE: Committee = {
  id: "c1",
  kind: "osms",
  name: "Охрана труда — цех 1",
  description: null,
  is_active: true,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const MEMBERS: MemberDetail[] = [
  { id: "mem1", committee_id: "c1", person_id: "p1", role: "chair", person_fio: "Иванов Иван" },
  { id: "mem2", committee_id: "c1", person_id: "p2", role: "secretary", person_fio: "Петров Пётр" },
  { id: "mem3", committee_id: "c1", person_id: "p3", role: "member", person_fio: "Сидоров Сидор" },
  { id: "mem4", committee_id: "c1", person_id: "p4", role: "member", person_fio: "Кузнецов Кузьма" },
];

const PLANNED_MEETING: Meeting = {
  id: "m1",
  committee_id: "c1",
  scheduled_at: "2026-07-20T09:00:00Z",
  location: "Каб. 1",
  status: "planned",
};

const HELD_MEETING: Meeting = {
  id: "m1",
  committee_id: "c1",
  scheduled_at: "2026-07-20T09:00:00Z",
  location: "Каб. 1",
  status: "held",
  held_at: "2026-07-20T09:30:00Z",
  protocol_seq: 1,
  protocol_year: 2026,
  members_total: 4,
  present_count: 3,
  quorum_met: true,
  protocol_no: "1/2026",
};

// present = p1, p2, p3 → 3 of 4 → quorum (3*2 > 4)
const ATTENDANCE_3: Attendance[] = [
  { id: "a1", meeting_id: "m1", person_id: "p1", present: true },
  { id: "a2", meeting_id: "m1", person_id: "p2", present: true },
  { id: "a3", meeting_id: "m1", person_id: "p3", present: true },
  { id: "a4", meeting_id: "m1", person_id: "p4", present: false },
];

const EMPTY_PROTOCOL: Protocol = { meeting: PLANNED_MEETING, decisions: [] };

const HELD_PROTOCOL_CARRIED: Protocol = {
  meeting: HELD_MEETING,
  decisions: [
    {
      decision: { id: "d1", text: "Решение о выдаче СИЗ", decided_at: "2026-07-20T09:35:00Z" },
      tasks: [],
      votes_for: 2,
      votes_against: 1,
      votes_abstain: 0,
      outcome: "carried",
      votes: [],
    },
  ],
};

const JOURNAL_ITEM: ProtocolJournalItem = {
  meeting_id: "m9",
  committee_id: "c9",
  committee_name: "Пожарная безопасность — склад",
  protocol_no: "1/2026",
  held_at: "2026-07-18T10:00:00Z",
  members_total: 4,
  present_count: 3,
  decisions_count: 1,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <CommitteesPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.list.mockResolvedValue({ items: [COMMITTEE], total: 1, limit: 100, offset: 0 });
  api.listMembers.mockResolvedValue(MEMBERS);
  api.listMeetings.mockResolvedValue({ items: [PLANNED_MEETING], total: 1, limit: 100, offset: 0 });
  api.getAttendance.mockResolvedValue(ATTENDANCE_3);
  api.getProtocol.mockResolvedValue(EMPTY_PROTOCOL);
  api.listProtocols.mockResolvedValue({ items: [JOURNAL_ITEM], total: 1, limit: 100, offset: 0 });
  api.holdMeeting.mockResolvedValue(HELD_MEETING);
  api.putAttendance.mockResolvedValue(ATTENDANCE_3);
  api.createCommittee.mockResolvedValue(COMMITTEE);
  api.addMember.mockResolvedValue({ id: "mem5", committee_id: "c1", person_id: "p5", role: "member" });
  api.removeMember.mockResolvedValue(undefined);
  api.createMeeting.mockResolvedValue(PLANNED_MEETING);
  api.createDecision.mockResolvedValue({ id: "d1", text: "Решение о выдаче СИЗ" });
  api.createTask.mockResolvedValue({ id: "t1", decision_id: "d1", status: "open", is_overdue: false });
  api.castVote.mockResolvedValue({ id: "v1", decision_id: "d1", person_id: "p1", choice: "for" });
});

async function selectCommitteeAndMeeting() {
  renderPage();
  fireEvent.click(await screen.findByText("Охрана труда — цех 1"));
  fireEvent.click(await screen.findByText("Каб. 1"));
}

describe("CommitteesPage срез-2", () => {
  it("renders committees and selecting one reveals members and meetings", async () => {
    renderPage();

    fireEvent.click(await screen.findByText("Охрана труда — цех 1"));

    // MembersPanel loaded for the selected committee
    const chairName = await screen.findByText("Иванов Иван");
    expect(chairName).toBeInTheDocument();
    // Role label rendered in the member's row ("Председатель" also appears in the
    // add-member role <select>, so scope to the row to disambiguate).
    expect(
      within(chairName.closest("tr") as HTMLElement).getByText("Председатель"),
    ).toBeInTheDocument();
    // MeetingList loaded
    expect(await screen.findByText("Каб. 1")).toBeInTheDocument();
    expect(api.listMembers).toHaveBeenCalledWith("c1");
    expect(api.listMeetings).toHaveBeenCalledWith("c1");
  });

  it("renders an attendance checkbox per member for a planned meeting", async () => {
    await selectCommitteeAndMeeting();

    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(MEMBERS.length);
  });

  it("shows the quorum indicator and flips between «есть» and «нет»", async () => {
    await selectCommitteeAndMeeting();

    const indicator = await screen.findByTestId("quorum-indicator");
    expect(indicator).toHaveTextContent("Присутствует 3 из 4");
    expect(indicator).toHaveTextContent("кворум есть");

    // Uncheck one present member → 2 of 4 → no quorum
    fireEvent.click(screen.getByLabelText(/Иванов Иван/));
    await waitFor(() => expect(indicator).toHaveTextContent("кворум нет"));
  });

  it("calls holdMeeting when «Провести заседание» is clicked", async () => {
    await selectCommitteeAndMeeting();

    fireEvent.click(await screen.findByRole("button", { name: "Провести заседание" }));

    await waitFor(() => expect(api.holdMeeting).toHaveBeenCalledWith("m1"));
  });

  it("surfaces the server message when holdMeeting returns 409", async () => {
    api.holdMeeting.mockRejectedValue({
      status: 409,
      code: "COMMITTEE_QUORUM_NOT_MET",
      message: "Кворум не набран",
      field_errors: [],
    });
    await selectCommitteeAndMeeting();

    fireEvent.click(await screen.findByRole("button", { name: "Провести заседание" }));

    expect(await screen.findByText("Кворум не набран")).toBeInTheDocument();
  });

  it("renders the protocol journal and shows the outcome badge for a held decision", async () => {
    renderPage();

    // Journal renders on mount
    const journalRow = await screen.findByText("Пожарная безопасность — склад");
    expect(journalRow).toBeInTheDocument();
    expect(within(journalRow.closest("tr") as HTMLElement).getByText("1/2026")).toBeInTheDocument();

    // Clicking a journal row selects that protocol → outcome badge is shown
    api.getProtocol.mockResolvedValue(HELD_PROTOCOL_CARRIED);
    fireEvent.click(journalRow);

    expect(await screen.findByText("Решение о выдаче СИЗ")).toBeInTheDocument();
    expect(await screen.findByText("Принято")).toBeInTheDocument();
  });

  it("renders «Отклонено» for a rejected decision outcome", async () => {
    api.getProtocol.mockResolvedValue({
      meeting: HELD_MEETING,
      decisions: [
        {
          decision: { id: "d2", text: "Спорное решение", decided_at: null },
          tasks: [],
          votes_for: 1,
          votes_against: 1,
          votes_abstain: 0,
          outcome: "rejected",
          votes: [],
        },
      ],
    });
    renderPage();

    fireEvent.click(await screen.findByText("Пожарная безопасность — склад"));

    expect(await screen.findByText("Отклонено")).toBeInTheDocument();
  });
});
