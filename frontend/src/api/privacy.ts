import { apiClient } from "@/api/client";

/**
 * Контур персональных данных (152-ФЗ). Срез-208: первая витрина у модуля,
 * который до этого жил только ручками.
 *
 * Здесь пока ТОЛЬКО реестр утечек — у него единственного идёт срок в ЧАСАХ
 * (24 на уведомление Роскомнадзора, 72 на результаты расследования), и цена
 * пропуска измеряется деньгами. Остальные права субъекта (выгрузка, журнал
 * доступа, согласия) по-прежнему без экрана — это названо остатком, а не
 * замолчано.
 */

export type BreachStage =
  | "notify_regulator"
  | "report_findings"
  | "notify_subjects";

export interface BreachDeadlineDto {
  stage: BreachStage;
  /** Подпись приходит с сервера: витрина не переводит коды сама. */
  title: string;
  due_at: string | null;
  done_at: string | null;
  status: "done" | "pending" | "overdue" | "no_deadline";
  status_title: string;
  /** Часы, а не дни: округление до даты дарит или отнимает часы. */
  hours_left: number | null;
}

export interface PdnBreachDto {
  id: string;
  summary: string;
  discovered_at: string | null;
  happened_at: string | null;
  affected_people: number | null;
  deadlines: BreachDeadlineDto[];
}

export interface PdnBreachListDto {
  items: PdnBreachDto[];
  /** Честная строка «платформа не отправляет уведомления сама». */
  notice: string;
}

export interface PdnBreachCreateDto {
  summary: string;
  discovered_at: string;
  happened_at?: string | null;
  affected_people?: number | null;
}

export const privacyApi = {
  breaches: async (): Promise<PdnBreachListDto> => {
    const { data } = await apiClient.get<PdnBreachListDto>("/privacy/breaches");
    return data;
  },
  registerBreach: async (
    payload: PdnBreachCreateDto,
  ): Promise<PdnBreachDto> => {
    const { data } = await apiClient.post<PdnBreachDto>(
      "/privacy/breaches",
      payload,
    );
    return data;
  },
  markBreachStep: async (
    breachId: string,
    stage: BreachStage,
  ): Promise<PdnBreachDto> => {
    const { data } = await apiClient.post<PdnBreachDto>(
      `/privacy/breaches/${breachId}/steps/${stage}`,
      {},
    );
    return data;
  },
};
