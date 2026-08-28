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

export type RoadSafetyReadinessDto = {
  total_vehicles: number;
  by_status: Record<string, number>;
  inspection_overdue: number;
  insurance_overdue: number;
  tachograph_overdue: number;
  /** ТС в эксплуатации без внесённых сведений — факт о данных, не вердикт. */
  documents_missing: number;
};

export const roadSafetyApi = {
  listVehicles: async (): Promise<VehicleDto[]> => {
    const { data } = await apiClient.get<{ items?: VehicleDto[] }>(
      "/road-safety/vehicles",
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
