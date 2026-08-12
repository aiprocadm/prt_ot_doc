import { apiClient } from "@/api/client";

/** Юридические тексты арендатора (ТЗ Доп. №1 разд. 52.2, четвёртый пункт). */
export type LegalDocumentKind = "offer" | "privacy" | "consent";

export interface LegalDocumentSummary {
  kind: LegalDocumentKind;
  title: string;
  version: number;
  /** Чей текст: `self` | `reseller`. */
  source: string;
  published_at: string;
}

export interface LegalDocument extends LegalDocumentSummary {
  body: string;
}

/**
 * Список действующих текстов. БЕЗ токена: оферту и политику ПДн человек обязан
 * прочитать ДО входа, иначе ссылка на них бессмысленна.
 */
export const listLegalDocuments = async (): Promise<LegalDocumentSummary[]> =>
  (await apiClient.get<{ items: LegalDocumentSummary[] }>("/public/legal")).data
    .items;

export const getLegalDocument = async (
  kind: LegalDocumentKind,
): Promise<LegalDocument> =>
  (await apiClient.get<LegalDocument>(`/public/legal/${kind}`)).data;
