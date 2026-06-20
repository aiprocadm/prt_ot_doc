import { apiClient } from "@/api/client";
import type {
  ReadinessReportDto, WorkPermitBriefingDto, WorkPermitDto, WorkPermitEventDto,
  WorkPermitMemberDto, WorkPermitPage, WorkPermitSignatureDto,
} from "@/types/dto/workPermits";

export interface PersonOption { id: string; label: string; }

export interface WorkPermitListParams {
  status?: string; work_type?: string; site_id?: string; limit?: number; offset?: number;
}

const base = "/work-permits";

export const workPermitsApi = {
  async list(params: WorkPermitListParams = {}): Promise<WorkPermitPage> {
    const r = await apiClient.get<WorkPermitPage>(base, {
      params: { limit: 200, offset: 0, ...params },
    });
    return r.data;
  },
  async count(params: WorkPermitListParams = {}): Promise<number> {
    const r = await apiClient.get<WorkPermitPage>(base, { params: { ...params, limit: 1, offset: 0 } });
    return r.data.total ?? 0;
  },
  async get(id: string): Promise<WorkPermitDto> {
    return (await apiClient.get<WorkPermitDto>(`${base}/${id}`)).data;
  },
  async create(body: Record<string, unknown>): Promise<WorkPermitDto> {
    return (await apiClient.post<WorkPermitDto>(base, body)).data;
  },
  async update(id: string, body: Record<string, unknown>): Promise<WorkPermitDto> {
    return (await apiClient.patch<WorkPermitDto>(`${base}/${id}`, body)).data;
  },
  async remove(id: string): Promise<void> {
    await apiClient.delete(`${base}/${id}`);
  },
  async addMember(id: string, body: { person_id: string; role: string }): Promise<WorkPermitMemberDto> {
    return (await apiClient.post<WorkPermitMemberDto>(`${base}/${id}/members`, body)).data;
  },
  async removeMember(id: string, memberId: string): Promise<void> {
    await apiClient.delete(`${base}/${id}/members/${memberId}`);
  },
  async readiness(id: string): Promise<ReadinessReportDto> {
    return (await apiClient.get<ReadinessReportDto>(`${base}/${id}/readiness`)).data;
  },
  async events(id: string): Promise<WorkPermitEventDto[]> {
    return (await apiClient.get<WorkPermitEventDto[]>(`${base}/${id}/events`)).data;
  },
  async action(
    id: string, name: "issue" | "suspend" | "resume" | "close" | "cancel",
    body: { note?: string } = {},
  ): Promise<WorkPermitDto> {
    return (await apiClient.post<WorkPermitDto>(`${base}/${id}/${name}`, body)).data;
  },
  async extend(id: string, planned_end: string): Promise<WorkPermitDto> {
    return (await apiClient.post<WorkPermitDto>(`${base}/${id}/extend`, { planned_end })).data;
  },
  async getBriefings(id: string): Promise<WorkPermitBriefingDto[]> {
    return (await apiClient.get<WorkPermitBriefingDto[]>(`${base}/${id}/briefing`)).data;
  },
  async createBriefing(id: string, body: Record<string, unknown>): Promise<WorkPermitBriefingDto> {
    return (await apiClient.post<WorkPermitBriefingDto>(`${base}/${id}/briefing`, body)).data;
  },
  async updateBriefing(
    id: string, briefingId: string, body: Record<string, unknown>,
  ): Promise<WorkPermitBriefingDto> {
    return (await apiClient.patch<WorkPermitBriefingDto>(`${base}/${id}/briefing/${briefingId}`, body)).data;
  },
  async listSignatures(id: string): Promise<WorkPermitSignatureDto[]> {
    return (await apiClient.get<WorkPermitSignatureDto[]>(`${base}/${id}/signatures`)).data;
  },
  async createPermitSignature(
    id: string, body: { person_id: string; mode: "attested" | "code" },
  ): Promise<WorkPermitSignatureDto> {
    return (await apiClient.post<WorkPermitSignatureDto>(`${base}/${id}/signatures`, body)).data;
  },
  async createBriefingSignature(
    id: string, briefingId: string, body: { person_id: string; mode: "attested" | "code" },
  ): Promise<WorkPermitSignatureDto> {
    return (await apiClient.post<WorkPermitSignatureDto>(
      `${base}/${id}/briefing/${briefingId}/signatures`, body,
    )).data;
  },
  async confirmSignatureCode(requestId: string, code: string): Promise<void> {
    await apiClient.post(`/sign/pep/requests/${requestId}/confirm`, { code });
  },
};

export async function fetchAllPersons(): Promise<PersonOption[]> {
  const r = await apiClient.get<{ items: Array<Record<string, unknown>> }>("/persons", {
    params: { limit: 200, offset: 0 }, // server cap is le=200; >200 persons → Ф1 follow-up
  });
  return (r.data.items ?? []).map((p) => {
    const last = (p.last_name as string) ?? "";
    const first = (p.first_name as string) ?? "";
    const middle = (p.middle_name as string) ?? "";
    const label = [last, first, middle].filter(Boolean).join(" ").trim() || (p.id as string);
    return { id: p.id as string, label };
  });
}
