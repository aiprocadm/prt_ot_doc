import { apiClient } from "@/api/client";

export interface BriefingTemplateDto {
  id: string;
  code: string;
  title: string;
  briefing_type: string;
  status: string;
  description?: string | null;
  validity_days?: number | null;
}

export interface BriefingJournalDto {
  id: string;
  code: string;
  title: string;
  journal_type: string;
  status: string;
}

export interface BriefingSignatureDto {
  id: string;
  signer_type: string;
  signer_user_id?: string | null;
  signature_mode: string;
  signed_at: string;
}

export interface BriefingEntryDto {
  id: string;
  briefing_journal_id: string;
  briefing_template_id?: string | null;
  person_id?: string | null;
  instructor_user_id?: string | null;
  briefing_type: string;
  briefing_date: string;
  valid_until?: string | null;
  reason?: string | null;
  status: string;
  notes?: string | null;
  signatures: BriefingSignatureDto[];
  is_overdue: boolean;
}

interface CollectionResponse<T> {
  items: T[];
  total: number;
}

export const briefingsApi = {
  async listTemplates() {
    const { data } = await apiClient.get<CollectionResponse<BriefingTemplateDto>>("/briefings/templates");
    return data.items;
  },
  async listJournals() {
    const { data } = await apiClient.get<CollectionResponse<BriefingJournalDto>>("/briefings/journals");
    return data.items;
  },
  async listEntries() {
    const { data } = await apiClient.get<CollectionResponse<BriefingEntryDto>>("/briefings/entries");
    return data.items;
  },
  async listOverdue() {
    const { data } = await apiClient.get<CollectionResponse<BriefingEntryDto>>("/briefings/entries/overdue");
    return data.items;
  },
  async createTemplate(payload: Omit<BriefingTemplateDto, "id">) {
    const { data } = await apiClient.post<BriefingTemplateDto>("/briefings/templates", payload);
    return data;
  },
  async createJournal(payload: Omit<BriefingJournalDto, "id"> & { site_id?: string | null; department_id?: string | null }) {
    const { data } = await apiClient.post<BriefingJournalDto>("/briefings/journals", payload);
    return data;
  },
  async createEntry(payload: Omit<BriefingEntryDto, "id" | "signatures" | "is_overdue">) {
    const { data } = await apiClient.post<BriefingEntryDto>("/briefings/entries", payload);
    return data;
  },
  async sign(entryId: string, signerType: "employee" | "instructor", signer_user_id?: string) {
    const { data } = await apiClient.post(`/briefings/entries/${entryId}/sign-${signerType}`, { signer_user_id });
    return data;
  },
  async complete(entryId: string) {
    const { data } = await apiClient.post<BriefingEntryDto>(`/briefings/entries/${entryId}/complete`);
    return data;
  },
  async remindOverdue() {
    const { data } = await apiClient.post<{ count: number; items: BriefingEntryDto[] }>("/briefings/entries/remind-overdue");
    return data;
  }
};
