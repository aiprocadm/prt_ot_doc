import { apiClient } from "@/api/client";

// ── Types ──────────────────────────────────────────────────────────────────

export interface Committee {
  id: string;
  kind: string;
  name: string;
  description?: string | null;
  is_active: boolean;
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
}

export interface MeetingPage {
  items: Meeting[];
  total: number;
  limit: number;
  offset: number;
}

export interface DecisionTask {
  id: string;
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
}

export interface Protocol {
  meeting: Meeting;
  decisions: ProtocolDecision[];
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
};
