import { apiClient } from "@/api/client";

/**
 * Контур ПромБеза (Доп. №1 разд. 54.2): реестр опасных производственных
 * объектов.
 *
 * Ручки гейтятся модулем `industrial_safety`: у арендатора без выдачи — 404, у
 * выдававшегося-отключённого чтение остаётся (read-only, BIZ-61).
 */

export type OpoHazardClass = "I" | "II" | "III" | "IV";

/**
 * Подписи классов — словами. Сервер отдаёт готовую подпись в `hazard_class_label`,
 * это запас для мест, где на руках только код (например, разрез сводки).
 */
export const OPO_HAZARD_CLASS_TITLES: Record<string, string> = {
  I: "I класс — чрезвычайно высокая опасность",
  II: "II класс — высокая опасность",
  III: "III класс — средняя опасность",
  IV: "IV класс — низкая опасность",
};

export type HazardousFacilityDto = {
  id: string;
  name: string;
  register_number: string;
  hazard_class: string;
  hazard_class_label: string;
  site_id?: string | null;
  registered_on?: string | null;
  excluded_on?: string | null;
  status: string;
  status_label: string;
  responsible?: string | null;
  notes?: string | null;
};

export type IndustrialReadinessDto = {
  total_facilities: number;
  /** Класс → число ДЕЙСТВУЮЩИХ объектов; ключи всегда все четыре. */
  by_class: Record<string, number>;
  excluded_facilities: number;
  /** Разд. 54.2: считаются только эксплуатируемые устройства. */
  total_devices: number;
  epb_overdue: number;
  epb_due_soon: number;
  /**
   * ФАКТ: назначенный срок службы истёк, действующего заключения ЭПБ нет.
   * ГРАНИЦА: платформа НЕ решает, обязана ли экспертиза быть проведена —
   * это зависит от типа устройства, документации и норм ФНП.
   */
  devices_past_lifetime_without_epb: number;
  /** Разд. 54.2 «история работ»: устройства без единой записи о работах. */
  devices_without_work_record: number;
  /** Разд. 54.2 «аттестация»: считаются только записи с областью из справочника. */
  attestations_total: number;
  attestations_overdue: number;
  attestations_due_soon: number;
  /**
   * Разд. 54.2 «производственный контроль». ГРАНИЦА: это ФАКТ наличия плана на
   * текущий год, а не приговор — обязанность вести ПК зависит от того,
   * эксплуатирует ли организация ОПО.
   */
  current_year_plan_exists: boolean;
  pc_measures_overdue: number;
  pc_measures_planned: number;
  /** Доп. №1 разд. 57.4: открытые происшествия этой дисциплины (срез-49). */
  incidents_open: number;
};

export type PcPlanDto = {
  id: string;
  year: number;
  title: string;
  responsible?: string | null;
  approved_on?: string | null;
  status: string;
  status_label: string;
  notes?: string | null;
  measures_total: number;
  measures_overdue: number;
};

export type PcMeasureDto = {
  id: string;
  plan_id: string;
  section: string;
  section_label: string;
  title: string;
  due_on: string;
  responsible?: string | null;
  /** planned | overdue | done | cancelled — «просрочено» считает сервер. */
  status: string;
  status_label: string;
  completed_on?: string | null;
  result?: string | null;
};

export type OpoAttestationDto = {
  id: string;
  person_id: string;
  person_name: string;
  name: string;
  area_code: string;
  area_label: string;
  issued_at?: string | null;
  expires_at?: string | null;
  /** ok | due_soon | overdue | absent — «срок не указан» отдельно. */
  validity_status: string;
  validity_status_label: string;
};

/** Подписи результатов работ — запас; перевод делает сервер. */
export const OPO_WORK_RESULT_TITLES: Record<string, string> = {
  passed: "Пригодно к эксплуатации",
  with_remarks: "Пригодно с условиями",
  failed: "Не пригодно",
};

export type DeviceWorkDto = {
  id: string;
  device_id: string;
  kind: string;
  kind_label: string;
  performed_on: string;
  result: string;
  result_label: string;
  performer?: string | null;
  conclusion_number?: string | null;
  notes?: string | null;
  next_due?: string | null;
  /** Перенесла ли работа срок эксплуатации; переносит только положительная ЭПБ. */
  shifted_due: boolean;
};

export type TechnicalDeviceDto = {
  id: string;
  facility_id: string;
  kind: string;
  kind_label: string;
  name: string;
  serial_number?: string | null;
  commissioned_on?: string | null;
  lifetime_until?: string | null;
  epb_conclusion_number?: string | null;
  epb_registered_on?: string | null;
  epb_valid_until?: string | null;
  status: string;
  status_label: string;
  notes?: string | null;
  /** ok | due_soon | overdue | absent — «нет заключения» отдельное состояние. */
  epb_status: string;
  epb_status_label: string;
  past_lifetime: boolean;
  /** Последняя подтверждённая работа: срок без неё — обещание, не доказательство. */
  last_work_on?: string | null;
  last_work_result?: string | null;
};

export const industrialSafetyApi = {
  listFacilities: async (): Promise<HazardousFacilityDto[]> => {
    const { data } = await apiClient.get<{ items?: HazardousFacilityDto[] }>(
      "/industrial-safety/facilities",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listDevices: async (): Promise<TechnicalDeviceDto[]> => {
    const { data } = await apiClient.get<{ items?: TechnicalDeviceDto[] }>(
      "/industrial-safety/devices",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listAttestations: async (): Promise<OpoAttestationDto[]> => {
    const { data } = await apiClient.get<{ items?: OpoAttestationDto[] }>(
      "/industrial-safety/attestations",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listPcPlans: async (): Promise<PcPlanDto[]> => {
    const { data } = await apiClient.get<{ items?: PcPlanDto[] }>(
      "/industrial-safety/pc-plans",
      { params: { limit: 50, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listPcMeasures: async (): Promise<PcMeasureDto[]> => {
    const { data } = await apiClient.get<{ items?: PcMeasureDto[] }>(
      "/industrial-safety/pc-measures",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  readiness: async (): Promise<IndustrialReadinessDto> => {
    const { data } = await apiClient.get<IndustrialReadinessDto>(
      "/industrial-safety/readiness",
    );
    return data;
  },
};
