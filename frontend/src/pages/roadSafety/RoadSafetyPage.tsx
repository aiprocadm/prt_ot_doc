import { type ColumnDef } from "@tanstack/react-table";
import { useCallback } from "react";

import { roadSafetyApi, type VehicleDto } from "@/api/roadSafety";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

/**
 * Срок документа ТС словами.
 *
 * Пустая дата — «сведения не внесены», а НЕ «бессрочно»: у диагностической
 * карты и полиса бессрочности не бывает. Поэтому в клетке стоит состояние из
 * ответа, а не прочерк.
 */
const dueCell = (due: string | null | undefined, label: string) =>
  due ? `${formatDate(due)} · ${label}` : label;

const VEHICLE_COLUMNS: ColumnDef<VehicleDto, unknown>[] = [
  { accessorKey: "plate_number", header: "Гос. номер" },
  { accessorKey: "brand_model", header: "Марка и модель" },
  {
    accessorKey: "kind_label",
    header: "Вид",
    cell: ({ row }) => row.original.kind_label,
  },
  {
    accessorKey: "status_label",
    header: "Состояние",
    cell: ({ row }) => row.original.status_label,
  },
  {
    accessorKey: "inspection_due",
    header: "Техосмотр",
    cell: ({ row }) =>
      dueCell(
        row.original.inspection_due,
        row.original.inspection_status_label,
      ),
  },
  {
    accessorKey: "insurance_due",
    header: "ОСАГО",
    cell: ({ row }) =>
      dueCell(row.original.insurance_due, row.original.insurance_status_label),
  },
  {
    accessorKey: "tachograph_status_label",
    header: "Тахограф",
    cell: ({ row }) => row.original.tachograph_status_label,
  },
];

/**
 * БДД: реестр транспортных средств (Доп. №1 разд. 56.2, срез-1).
 *
 * До этого экрана по разд. 56.2 не было НИЧЕГО: ТЗ отсылало к «transport
 * safety», которого в коде не существовало.
 */
const RoadSafetyPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        vehicles: await roadSafetyApi.listVehicles(),
        readiness: await roadSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      vehicles: [] as VehicleDto[],
      readiness: {
        total_vehicles: 0,
        by_status: { in_service: 0, suspended: 0, decommissioned: 0 },
        inspection_overdue: 0,
        insurance_overdue: 0,
        tachograph_overdue: 0,
        documents_missing: 0,
      },
    },
    errorMessage: "Не удалось загрузить реестр транспортных средств",
  });

  const registry = useLocalRegistry({
    items: data.vehicles,
    match: (item, query) =>
      [item.plate_number, item.brand_model, item.kind_label, item.status_label]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const { readiness } = data;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Безопасность дорожного движения"
        description="Реестр транспортных средств: учёт парка, сроки диагностической карты и полиса, поверка тахографа."
        stats={[
          { label: "Транспортных средств", value: readiness.total_vehicles },
          {
            label: "В эксплуатации",
            value: readiness.by_status.in_service ?? 0,
          },
          { label: "Списано", value: readiness.by_status.decommissioned ?? 0 },
          // Просрочки — ТОЛЬКО по эксплуатируемым: у списанной машины
          // просроченный полис это шум, а не проблема.
          { label: "Техосмотр просрочен", value: readiness.inspection_overdue },
          { label: "ОСАГО просрочено", value: readiness.insurance_overdue },
          // ФАКТ о данных, а не вердикт о нарушении.
          { label: "Сведения не внесены", value: readiness.documents_missing },
        ]}
      />

      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка парка" /> : null}
      {/*
        ГРАНИЦА, названная НА ЭКРАНЕ (прецедент категории НВОС и периодичности
        ПЭК): нужен ли тахограф и требуется ли лицензия, следует из вида
        перевозок, массы и категории ТС по закону — этих данных в системе нет.
      */}
      {!loading && !error ? (
        <p className="text-sm text-muted-foreground">
          Платформа ведёт учёт внесённого и не решает, нужен ли тахограф и
          требуется ли лицензия: это следует из вида перевозок, массы и
          категории ТС. Пустой срок означает «сведения не внесены», а не
          «бессрочно» — у полиса и диагностической карты бессрочности не бывает.
          Просрочки считаются только по машинам в эксплуатации.
        </p>
      ) : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Транспортные средства не заведены"
          description="Внесите парк: гос. номер, марку и вид ТС, сроки диагностической карты и полиса, наличие тахографа. Списание меняет состояние записи, а не удаляет её."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={VEHICLE_COLUMNS}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по номеру, марке, виду"
          caption="Реестр транспортных средств"
        />
      ) : null}
    </div>
  );
};

export default RoadSafetyPage;
