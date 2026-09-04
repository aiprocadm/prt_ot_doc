import { apiClient } from "@/api/client";

/**
 * Площадки и карточка площадки 360° (BIZ-54-57 срез-3, Доп. №1 разд. 57.1).
 *
 * Формы ответов повторяют светофор клиента (`managedClients.ts`): одна и та же
 * дисциплина на двух экранах обязана выглядеть одинаково.
 */

export type TrafficLight = "green" | "yellow" | "red" | "not_measured";

export interface Site {
  id: string;
  company_id: string;
  name: string;
  address?: string | null;
  hazard_class?: string | null;
  site_type?: string | null;
  is_hazardous_production_facility: boolean;
  opo_register_number?: string | null;
}

export interface SitePage {
  items: Site[];
  total: number;
}

export interface SiteDiscipline {
  discipline: string;
  title: string;
  /** not_measured — не цвет, а честное «эталона нет». */
  light: TrafficLight;
  reason: string;
  required: number;
  missing: number;
  lapsed: number;
  expiring: number;
}

export interface SitePermitFacts {
  total: number;
  /** Дисциплина → число действующих нарядов-допусков. */
  by_discipline: Record<string, number>;
  without_discipline: number;
  without_discipline_titles: string[];
  /** Почему у них нет дисциплины — иначе число читается как недоделка. */
  without_discipline_reason: string;
}

export interface SiteFacts {
  workplaces: number;
  people: number;
  /** Люди КОМПАНИИ без рабочего места: ни к одной площадке не отнесены. */
  people_without_workplace: number;
  permits: SitePermitFacts;
}

export interface SiteNotCounted {
  title: string;
  reason: string;
}

export interface SiteOverview {
  site_id: string;
  name: string;
  company_id: string;
  address?: string | null;
  hazard_class?: string | null;
  is_hazardous_production_facility: boolean;
  opo_register_number?: string | null;
  overall: TrafficLight;
  disciplines: SiteDiscipline[];
  facts: SiteFacts;
  /** Что привязано к площадке, но не посчитано — с причиной. */
  not_counted: SiteNotCounted[];
}

const base = "/sites";

// Ошибки показываются на самом экране (ErrorState), а не тостом: у площадки
// бывает 403 «только администратор», и такое объяснение обязано остаться перед
// глазами, а не погаснуть.
const silent = { silentApiErrorToast: true } as const;

export const sitesApi = {
  async list(
    params: { limit?: number; offset?: number } = {},
  ): Promise<SitePage> {
    const r = await apiClient.get<SitePage>(base, {
      params: { limit: 200, offset: 0, ...params },
      ...silent,
    });
    return r.data;
  },

  async overview(siteId: string): Promise<SiteOverview> {
    return (
      await apiClient.get<SiteOverview>(`${base}/${siteId}/overview`, silent)
    ).data;
  },
};
