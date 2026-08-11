import { apiClient } from "@/api/client";

// ── Types ──────────────────────────────────────────────────────────────────

export interface Committee {
  id: string;
  kind: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  quorum_threshold_pct?: number | null;
  created_at: string;
  updated_at: string;
}

export interface CommitteePage {
  items: Committee[];
  total: number;
  limit: number;
  offset: number;
}

export interface Meeting {
  id: string;
  committee_id: string;
  scheduled_at: string;
  location?: string | null;
  status: string;
  held_at?: string | null;
  protocol_seq?: number | null;
  protocol_year?: number | null;
  members_total?: number | null;
  present_count?: number | null;
  quorum_met?: boolean | null;
  protocol_no?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface MeetingPage {
  items: Meeting[];
  total: number;
  limit: number;
  offset: number;
}

export interface DecisionTask {
  id: string;
  decision_id: string;
  assignee_person_id?: string | null;
  due_date?: string | null;
  status: string;
  evidence_note?: string | null;
  is_overdue: boolean;
}

export interface Decision {
  id: string;
  text: string;
  decided_at?: string | null;
  [key: string]: unknown;
}

export interface ProtocolDecision {
  decision: Decision;
  tasks: DecisionTask[];
  votes_for?: number;
  votes_against?: number;
  votes_abstain?: number;
  outcome?: "carried" | "rejected" | null;
  votes?: Vote[];
}

export interface Protocol {
  meeting: Meeting;
  decisions: ProtocolDecision[];
}

// ── Срез-2: attendance, votes, protocol journal ────────────────────────────

export interface MemberDetail {
  id: string;
  committee_id: string;
  person_id: string;
  role: string;
  person_fio?: string | null;
}

export interface Attendance {
  id: string;
  meeting_id: string;
  person_id: string;
  present: boolean;
}

export interface Invitation {
  id: string;
  meeting_id: string;
  person_id: string;
  invited_at: string;
}

/**
 * Клиентское зеркало правила кворума (срез-4): порог в процентах (включительно),
 * без порога — строго больше половины.
 */
export const clientQuorum = (
  presentCount: number,
  membersTotal: number,
  thresholdPct?: number | null,
): boolean => {
  if (membersTotal <= 0) return false;
  if (thresholdPct == null) return presentCount * 2 > membersTotal;
  return presentCount * 100 >= thresholdPct * membersTotal;
};

export type VoteChoice = "for" | "against" | "abstain";

export interface Vote {
  id: string;
  decision_id: string;
  person_id: string;
  choice: VoteChoice;
}

export interface DecisionVoteSummary {
  decision_id: string;
  votes_for: number;
  votes_against: number;
  votes_abstain: number;
  outcome: "carried" | "rejected";
  votes: Vote[];
}

export interface ProtocolJournalItem {
  meeting_id: string;
  committee_id: string;
  committee_name: string;
  protocol_no: string;
  held_at: string;
  members_total: number | null;
  present_count: number | null;
  decisions_count: number;
}

export interface ProtocolJournalPage {
  items: ProtocolJournalItem[];
  total: number;
  limit: number;
  offset: number;
}

// ── Срез-3: KPI dashboard ──────────────────────────────────────────────────

export interface CommitteeKpi {
  committees_total: number;
  committees_active: number;
  meetings_planned: number;
  meetings_held: number;
  meetings_cancelled: number;
  decisions_total: number;
  tasks_total: number;
  tasks_open: number;
  tasks_overdue: number;
  tasks_done: number;
  held_meetings: number;
  avg_attendance_pct: number;
  quorum_rate_pct: number;
}

// ── API ────────────────────────────────────────────────────────────────────

const base = "/committees";

export const committeesApi = {
  async list(params: { limit?: number; offset?: number } = {}): Promise<CommitteePage> {
    const r = await apiClient.get<CommitteePage>(base, {
      params: { limit: 100, offset: 0, ...params },
    });
    return r.data;
  },

  async get(id: string): Promise<Committee> {
    return (await apiClient.get<Committee>(`${base}/${id}`)).data;
  },

  async listMeetings(committeeId: string, params: { limit?: number; offset?: number } = {}): Promise<MeetingPage> {
    const r = await apiClient.get<MeetingPage>(`${base}/${committeeId}/meetings`, {
      params: { limit: 100, offset: 0, ...params },
    });
    return r.data;
  },

  async getProtocol(meetingId: string): Promise<Protocol> {
    return (await apiClient.get<Protocol>(`${base}/meetings/${meetingId}/protocol`)).data;
  },

  // ── Write helpers (срез-1 create/update) ──────────────────────────────

  async createCommittee(payload: {
    kind: string;
    name: string;
    description?: string | null;
    is_active?: boolean;
    quorum_threshold_pct?: number | null;
  }): Promise<Committee> {
    return (await apiClient.post<Committee>(base, payload)).data;
  },

  async updateCommittee(
    id: string,
    payload: {
      kind?: string;
      name?: string;
      description?: string | null;
      is_active?: boolean;
      quorum_threshold_pct?: number | null;
    },
  ): Promise<Committee> {
    return (await apiClient.patch<Committee>(`${base}/${id}`, payload)).data;
  },

  async addMember(
    committeeId: string,
    payload: { person_id: string; role?: string },
  ): Promise<{ id: string; committee_id: string; person_id: string; role: string }> {
    return (
      await apiClient.post<{ id: string; committee_id: string; person_id: string; role: string }>(
        `${base}/${committeeId}/members`,
        payload,
      )
    ).data;
  },

  async listMembers(committeeId: string): Promise<MemberDetail[]> {
    return (await apiClient.get<MemberDetail[]>(`${base}/${committeeId}/members`)).data;
  },

  async removeMember(committeeId: string, memberId: string): Promise<void> {
    await apiClient.delete(`${base}/${committeeId}/members/${memberId}`);
  },

  async createMeeting(
    committeeId: string,
    payload: { scheduled_at: string; location?: string | null },
  ): Promise<Meeting> {
    return (await apiClient.post<Meeting>(`${base}/${committeeId}/meetings`, payload)).data;
  },

  async createDecision(
    meetingId: string,
    payload: { text: string; agenda_item_id?: string | null },
  ): Promise<Decision> {
    return (await apiClient.post<Decision>(`${base}/meetings/${meetingId}/decisions`, payload)).data;
  },

  async createTask(
    decisionId: string,
    payload: { assignee_person_id?: string | null; due_date?: string | null; evidence_note?: string | null },
  ): Promise<DecisionTask> {
    return (await apiClient.post<DecisionTask>(`${base}/decisions/${decisionId}/tasks`, payload)).data;
  },

  async updateTask(
    taskId: string,
    payload: {
      assignee_person_id?: string | null;
      due_date?: string | null;
      status?: string;
      evidence_note?: string | null;
    },
  ): Promise<DecisionTask> {
    return (await apiClient.patch<DecisionTask>(`${base}/tasks/${taskId}`, payload)).data;
  },

  // ── Срез-2: attendance, quorum-hold, votes, protocol journal ──────────

  async getAttendance(meetingId: string): Promise<Attendance[]> {
    return (await apiClient.get<Attendance[]>(`${base}/meetings/${meetingId}/attendance`)).data;
  },

  async putAttendance(
    meetingId: string,
    items: { person_id: string; present: boolean }[],
  ): Promise<Attendance[]> {
    return (
      await apiClient.put<Attendance[]>(`${base}/meetings/${meetingId}/attendance`, { items })
    ).data;
  },

  // ── Срез-4: приглашения + печатная форма протокола ────────────────────

  async getInvitations(meetingId: string): Promise<Invitation[]> {
    return (await apiClient.get<Invitation[]>(`${base}/meetings/${meetingId}/invitations`)).data;
  },

  async putInvitations(meetingId: string, personIds: string[]): Promise<Invitation[]> {
    return (
      await apiClient.put<Invitation[]>(`${base}/meetings/${meetingId}/invitations`, {
        person_ids: personIds,
      })
    ).data;
  },

  async downloadProtocolPrint(
    meetingId: string,
    fmt: "docx" | "pdf",
    nameHint?: string,
  ): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${base}/meetings/${meetingId}/protocol/print`, {
      params: { format: fmt },
      responseType: "blob",
    });
    const url = URL.createObjectURL(data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `committee-protocol-${nameHint ?? meetingId}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  },

  async holdMeeting(meetingId: string): Promise<Meeting> {
    return (await apiClient.patch<Meeting>(`${base}/meetings/${meetingId}`, { status: "held" })).data;
  },

  async castVote(decisionId: string, person_id: string, choice: VoteChoice): Promise<Vote> {
    return (
      await apiClient.post<Vote>(`${base}/decisions/${decisionId}/votes`, { person_id, choice })
    ).data;
  },

  async getVotes(decisionId: string): Promise<DecisionVoteSummary> {
    return (await apiClient.get<DecisionVoteSummary>(`${base}/decisions/${decisionId}/votes`)).data;
  },

  async listProtocols(
    params: { committee_id?: string; limit?: number; offset?: number } = {},
  ): Promise<ProtocolJournalPage> {
    const r = await apiClient.get<ProtocolJournalPage>(`${base}/protocols`, {
      params: { limit: 100, offset: 0, ...params },
    });
    return r.data;
  },

  async getKpi(params: { committee_id?: string } = {}): Promise<CommitteeKpi> {
    const r = await apiClient.get<CommitteeKpi>(`${base}/kpi`, { params });
    return r.data;
  },
};
