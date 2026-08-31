import { apiClient } from "@/api/client";

/**
 * Контур БДД (Доп. №1 разд. 56.2, срез-1): реестр транспортных средств.
 *
 * ГРАНИЦА: платформа не решает, нужен ли тахограф и требуется ли лицензия —
 * это следует из вида перевозок, массы и категории ТС по закону. Полей
 * «требуется тахограф» и «соответствует ли ТС» в ответах нет.
 */
export type VehicleDto = {
  id: string;
  plate_number: string;
  brand_model: string;
  kind: string;
  kind_label: string;
  status: string;
  status_label: string;
  vin?: string | null;
  year_made?: number | null;
  site_id?: string | null;
  inspection_due?: string | null;
  insurance_due?: string | null;
  license_number?: string | null;
  license_due?: string | null;
  tachograph_installed: boolean;
  tachograph_due?: string | null;
  notes?: string | null;
  /**
   * missing | ok | due_soon | overdue. Пустой срок означает «сведения не
   * внесены», а НЕ «бессрочно»: у полиса и диагностической карты
   * бессрочности не бывает.
   */
  inspection_status: string;
  inspection_status_label: string;
  insurance_status: string;
  insurance_status_label: string;
  /** not_installed | missing | ok | due_soon | overdue. */
  tachograph_status: string;
  tachograph_status_label: string;
};

/**
 * Срез-2: карточка водителя. ФИО приходит из ядрового справочника людей и
 * здесь НЕ хранится — второй список сотрудников разошёлся бы с первым.
 *
 * ГРАНИЦА: полей «допущен ли к этой машине» и «хватает ли стажа» нет —
 * нужная категория и требуемый стаж следуют из массы ТС, числа мест и вида
 * перевозок по закону.
 */
export type DriverDto = {
  id: string;
  person_id: string;
  person_name: string;
  personnel_number?: string | null;
  position_title?: string | null;
  license_number: string;
  categories: string[];
  /** те же категории словами — экран не знает справочника */
  category_labels: string[];
  license_issued_at?: string | null;
  license_due?: string | null;
  experience_since?: string | null;
  /**
   * Стаж СЧИТАЕТСЯ сервером при чтении от даты начала; null — дата не
   * внесена. Числом стаж не хранится: записанное «3 года» через два года
   * молча становится ложью.
   */
  experience_years?: number | null;
  status: string;
  status_label: string;
  /** missing | ok | due_soon | overdue — пустой срок это «сведений нет». */
  license_status: string;
  license_status_label: string;
  notes?: string | null;
};

/**
 * Срез-3: путевой лист. Госномер и ФИО приходят из реестров и в листе НЕ
 * хранятся — переименование машины иначе оставило бы старое имя в тысяче
 * листов.
 *
 * ГРАНИЦА: полей «законен ли выпуск», «время за рулём» и «превышено ли
 * время» нет. Считается ВРЕМЯ В РЕЙСЕ; сколько из него человек реально вёл
 * машину и уложился ли он в режим труда и отдыха, платформа не знает.
 */
export type WaybillDto = {
  id: string;
  number: string;
  vehicle_id: string;
  vehicle_plate: string;
  vehicle_brand_model: string;
  driver_id: string;
  driver_name: string;
  driver_license_number: string;
  issued_on: string;
  departure_at?: string | null;
  return_at?: string | null;
  /** Считается сервером из пары выезд/возвращение; null — дат нет. */
  trip_hours?: number | null;
  /**
   * not_recorded | passed | failed — ТРИ значения, а не флажок: «сведений
   * нет» и «не пройден» это разные факты.
   */
  pre_trip_medical: string;
  pre_trip_medical_label: string;
  post_trip_medical: string;
  post_trip_medical_label: string;
  pre_trip_technical: string;
  pre_trip_technical_label: string;
  /**
   * confirmed | unconfirmed | blocked — считается сервером из ДВУХ
   * обязательных отметок. Послерейсовый осмотр в вердикт не входит: он
   * обязателен не всем.
   */
  release_status: string;
  release_status_label: string;
  status: string;
  status_label: string;
  notes?: string | null;
};

export type RoadSafetyReadinessDto = {
  total_vehicles: number;
  by_status: Record<string, number>;
  inspection_overdue: number;
  insurance_overdue: number;
  tachograph_overdue: number;
  /** ТС в эксплуатации без внесённых сведений — факт о данных, не вердикт. */
  documents_missing: number;
  /** Срез-2: водительский состав. Просрочки — только по ДОПУЩЕННЫМ. */
  total_drivers: number;
  drivers_by_status: Record<string, number>;
  driver_license_overdue: number;
  /** Допущенные без внесённого срока — факт о данных, не вердикт. */
  driver_license_missing: number;
  /**
   * Срез-3: путевые листы. Считаются ЗА ОКНО, а не за всё время — реестр
   * растёт каждую смену, в отличие от парка и водительского состава.
   */
  waybill_window_days: number;
  waybills_total: number;
  waybills_by_status: Record<string, number>;
  /** Обязательная отметка НЕ ПРОЙДЕНА — выпуск с нарушением. */
  waybills_release_blocked: number;
  /** Обязательная отметка не внесена — дыра в учёте, а НЕ нарушение. */
  waybills_release_unconfirmed: number;
};

export const roadSafetyApi = {
  listVehicles: async (): Promise<VehicleDto[]> => {
    const { data } = await apiClient.get<{ items?: VehicleDto[] }>(
      "/road-safety/vehicles",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listDrivers: async (): Promise<DriverDto[]> => {
    const { data } = await apiClient.get<{ items?: DriverDto[] }>(
      "/road-safety/drivers",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },
  listWaybills: async (): Promise<WaybillDto[]> => {
    const { data } = await apiClient.get<{ items?: WaybillDto[] }>(
      "/road-safety/waybills",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },
  readiness: async (): Promise<RoadSafetyReadinessDto> => {
    const { data } = await apiClient.get<RoadSafetyReadinessDto>(
      "/road-safety/readiness",
    );
    return data;
  },
};
