import { apiClient } from "@/api/client";

/**
 * Самостоятельная регистрация (BIZ-53 срез-3, разд. 53.2).
 *
 * Ручка ПУБЛИЧНАЯ: у регистрирующегося ещё нет рабочего пространства, поэтому
 * заголовок арендатора он поставить не может. Она же выключена по умолчанию и
 * тогда отвечает 404 — экран объясняет это словами, а не общей ошибкой.
 */

export type SignupPayload = {
  slug: string;
  company_name: string;
  owner_email: string;
  owner_password: string;
  industry?: string | null;
};

export type SignupResult = {
  tenant_slug: string;
  owner_email: string;
  /** Стартовая редакция: полный набор продаётся, а не раздаётся. */
  plan_code: string;
  /** Предупреждения выдачи — например, «отраслевого набора нет». */
  warnings: string[];
};

export const signup = async (payload: SignupPayload): Promise<SignupResult> => {
  const { data } = await apiClient.post<SignupResult>(
    "/public/signup",
    payload,
    // Ошибку показывает сам экран: «регистрация закрыта» и «адрес занят» —
    // это объяснения, а не сбои, и тостом они гаснут раньше, чем их прочтут.
    { silentApiErrorToast: true },
  );
  return data;
};
