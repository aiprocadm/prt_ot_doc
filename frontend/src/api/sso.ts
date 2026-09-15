import { apiClient } from "@/api/client";

/**
 * Единый вход (срез-204, BIZ-53 разд. 53.3).
 *
 * Обе ручки ПУБЛИЧНЫЕ: у входящего ещё нет токена. Ошибки гасятся от общего
 * всплывающего сообщения (`silentApiErrorToast`) — причину отказа показывает
 * сам экран входа, словами с сервера, и дублировать её всплывашкой значит
 * сказать человеку одно и то же дважды.
 */

export interface SsoStatusDto {
  enabled: boolean;
}

export interface SsoStartDto {
  authorization_url: string;
}

export const ssoApi = {
  status: async (tenantSlug: string): Promise<SsoStatusDto> => {
    const { data } = await apiClient.get<SsoStatusDto>(
      `/auth/sso/${encodeURIComponent(tenantSlug)}/status`,
      { silentApiErrorToast: true },
    );
    return data;
  },
  start: async (tenantSlug: string): Promise<SsoStartDto> => {
    const { data } = await apiClient.get<SsoStartDto>(
      `/auth/sso/${encodeURIComponent(tenantSlug)}/start`,
      { silentApiErrorToast: true },
    );
    return data;
  },
};
