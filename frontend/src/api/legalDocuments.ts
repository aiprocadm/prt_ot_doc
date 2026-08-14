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

/** Состояние принятия одного вида текста текущим пользователем (срез-11). */
export interface LegalAcceptanceStatus {
  kind: LegalDocumentKind;
  title: string | null;
  current_version: number | null;
  accepted_version: number | null;
  accepted_at: string | null;
  accepted: boolean;
  /** Принята прежняя редакция, вышла новая — «условия изменились». */
  outdated: boolean;
}

export interface LegalAcceptanceState {
  items: LegalAcceptanceStatus[];
  /** Что ещё требует подписи. Считает сервер: вычислять на фронте значит
   *  завести вторую правду о том, подписан ли документ. */
  pending: LegalDocumentKind[];
}

/** Что ждёт подписи. С токеном: подписывает конкретный человек. */
export const getLegalAcceptanceState = async (): Promise<LegalAcceptanceState> =>
  (await apiClient.get<LegalAcceptanceState>("/legal/acceptance")).data;

/** Принять действующую редакцию. Номер и текст сервер берёт сам. */
export const acceptLegalDocument = async (
  kind: LegalDocumentKind,
): Promise<void> => {
  await apiClient.post(`/legal/acceptance/${kind}`);
};
