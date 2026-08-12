import { apiClient } from "@/api/client";

/**
 * Бренд ПРИЛОЖЕНИЯ (ТЗ Доп. №1 разд. 52.2).
 *
 * Отдельный файл от `api/branding.ts` намеренно: тот про бренд ДОКУМЕНТОВ
 * (бланки, реквизиты, печати, подписанты) и живёт на уровне организации.
 * Здесь — имя, цвет и почта самого приложения на уровне арендатора. Сложи их
 * вместе — и «бренд» начнёт означать в коде две разные вещи.
 */
export interface AppBrand {
  app_name: string;
  primary_color: string;
  support_email: string | null;
  /** Откуда бренд: `self` | `reseller` | `platform`. */
  source: string;
}

export interface TenantBrandingDto {
  app_name: string | null;
  primary_color: string | null;
  support_email: string | null;
  effective: AppBrand;
}

/**
 * Действующий бренд арендатора. БЕЗ токена: бренд нужен экрану входа, а на нём
 * токена ещё нет. Отдай его только после входа — и человек увидит сначала
 * вендора, а потом подмену, то есть ровно то, что разд. 52.2 запрещает.
 */
export const getAppBrand = async (): Promise<AppBrand> =>
  (await apiClient.get<AppBrand>("/public/branding")).data;

export const getOwnAppBranding = async (): Promise<TenantBrandingDto> =>
  (await apiClient.get<TenantBrandingDto>("/platform/branding")).data;

export const saveOwnAppBranding = async (payload: {
  app_name: string | null;
  primary_color: string | null;
  support_email: string | null;
}): Promise<TenantBrandingDto> =>
  (await apiClient.put<TenantBrandingDto>("/platform/branding", payload)).data;
