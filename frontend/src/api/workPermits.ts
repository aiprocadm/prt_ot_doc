import { apiClient } from "@/api/client";
import type {
  ReadinessReportDto, WorkPermitBriefingDto, WorkPermitClosingSummaryDto,
  WorkPermitDailyAdmissionDto, WorkPermitDto,
  WorkPermitEventDto, WorkPermitMemberDto, WorkPermitPage, WorkPermitSignatureDto,
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
  async getClosing(id: string): Promise<WorkPermitClosingSummaryDto> {
    return (await apiClient.get<WorkPermitClosingSummaryDto>(`${base}/${id}/closing`)).data;
  },
  async recordCompletion(id: string, completionText: string): Promise<WorkPermitClosingSummaryDto> {
    return (await apiClient.post<WorkPermitClosingSummaryDto>(`${base}/${id}/closing`, { completion_text: completionText })).data;
  },
  async createClosingSignature(
    id: string, personId: string, mode: "attested" | "code",
  ): Promise<WorkPermitSignatureDto> {
    return (await apiClient.post<WorkPermitSignatureDto>(`${base}/${id}/closing/signatures`, { person_id: personId, mode })).data;
  },
  async listAdmissions(id: string): Promise<WorkPermitDailyAdmissionDto[]> {
    return (await apiClient.get<WorkPermitDailyAdmissionDto[]>(`${base}/${id}/admissions`)).data;
  },
  async createAdmission(id: string, body: Record<string, unknown>): Promise<WorkPermitDailyAdmissionDto> {
    return (await apiClient.post<WorkPermitDailyAdmissionDto>(`${base}/${id}/admissions`, body)).data;
  },
  async updateAdmission(
    id: string, admissionId: string, body: Record<string, unknown>,
  ): Promise<WorkPermitDailyAdmissionDto> {
    return (await apiClient.patch<WorkPermitDailyAdmissionDto>(`${base}/${id}/admissions/${admissionId}`, body)).data;
  },
  async downloadPrint(id: string, fmt: "docx" | "pdf", nameHint?: string): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${base}/${id}/print`, {
      params: { format: fmt }, responseType: "blob",
    });
    const url = URL.createObjectURL(data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `work-permit-${nameHint ?? id}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
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
