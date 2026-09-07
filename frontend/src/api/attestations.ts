import { apiClient } from "@/api/client";

/**
 * Ядровые аттестации (Доп. №1 разд. 54.2 «аттестация по промбезопасности»).
 *
 * Сущность ядровая, а не контурная: аттестации бывают и у других дисциплин
 * (проверка знаний ПДД у водителя — разд. 56.2). Контур отбирает СВОИ записи
 * по дисциплине области, а не по «поле заполнено» — поэтому ручки живут в
 * ядре (`/attestations`), а не в модуле ПромБеза.
 */

/**
 * Состояние аттестации — копия `AttestationStatus` бэкенда. «Истекла» ставится
 * руками так же, как «действует»: срок мог кончиться, а новую ещё не выдали.
 */
export const ATTESTATION_STATUS_TITLES: Record<string, string> = {
  active: "Действует",
  expired: "Истекла",
  revoked: "Отозвана",
};

/**
 * Области аттестации ПРОМБЕЗОПАСНОСТИ — копия справочника ядра
 * (`ATTESTATION_AREA_TITLES` без областей других дисциплин). Совпадение
 * стережёт `tests/test_opo_attestation.py` (срез-106): область, добавленная
 * только на бэкенде, не появилась бы в форме, а запись по ней не попала бы в
 * сводку контура.
 */
export const OPO_ATTESTATION_AREA_TITLES: Record<string, string> = {
  "А.1": "А.1 — общие требования промышленной безопасности",
  "Б.1":
    "Б.1 — химическая, нефтехимическая и нефтеперерабатывающая промышленность",
  "Б.2": "Б.2 — нефтяная и газовая промышленность",
  "Б.3": "Б.3 — металлургическая промышленность",
  "Б.4": "Б.4 — горнорудная промышленность",
  "Б.5": "Б.5 — угольная промышленность",
  "Б.6": "Б.6 — маркшейдерское обеспечение и охрана недр",
  "Б.7": "Б.7 — объекты газораспределения и газопотребления",
  "Б.8": "Б.8 — оборудование, работающее под избыточным давлением",
  "Б.9": "Б.9 — подъёмные сооружения",
  "Б.10": "Б.10 — транспортирование опасных веществ",
  "Б.11": "Б.11 — объекты хранения и переработки растительного сырья",
  "Б.12": "Б.12 — взрывные работы",
};

/** Тело аттестации: человек и название обязательны, область — из справочника. */
export type AttestationCreateInput = {
  person_id: string;
  name: string;
  area_code?: string | null;
  issued_at?: string | null;
  expires_at?: string | null;
  status?: string;
  notes?: string | null;
};

export type AttestationUpdateInput = AttestationCreateInput;

export type AttestationDto = {
  id: string;
  person_id: string;
  name: string;
  area_code?: string | null;
  area_label?: string | null;
  issued_at?: string | null;
  expires_at?: string | null;
  status: string;
  notes?: string | null;
};

export const attestationsApi = {
  create: async (body: AttestationCreateInput): Promise<AttestationDto> => {
    const { data } = await apiClient.post<AttestationDto>(
      "/attestations",
      body,
    );
    return data;
  },

  update: async (
    id: string,
    body: AttestationUpdateInput,
  ): Promise<AttestationDto> => {
    const { data } = await apiClient.patch<AttestationDto>(
      `/attestations/${id}`,
      body,
    );
    return data;
  },
};
