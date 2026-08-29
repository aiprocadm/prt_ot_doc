import { type ColumnDef } from "@tanstack/react-table";
import { useCallback, useState } from "react";

import {
  roadSafetyApi,
  type DriverDto,
  type VehicleDto,
} from "@/api/roadSafety";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

/**
 * Срок документа словами.
 *
 * Пустая дата — «сведения не внесены», а НЕ «бессрочно»: у диагностической
 * карты, полиса и водительского удостоверения бессрочности не бывает. Поэтому
 * в клетке стоит состояние из ответа, а не прочерк.
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

const DRIVER_COLUMNS: ColumnDef<DriverDto, unknown>[] = [
  // ФИО приходит из ядрового справочника людей: карточка водителя его не
  // хранит, иначе появился бы второй список сотрудников.
  { accessorKey: "person_name", header: "Водитель" },
  { accessorKey: "license_number", header: "Удостоверение" },
  {
    accessorKey: "categories",
    header: "Категории",
    // Категории из закрытого справочника: в клетке коды, расшифровка —
    // в подсказке, иначе строка не помещается.
    cell: ({ row }) => (
      <span title={row.original.category_labels.join("; ")}>
        {row.original.categories.join(", ")}
      </span>
    ),
  },
  {
    accessorKey: "experience_years",
    header: "Стаж",
    // Стаж СЧИТАЕТСЯ сервером от даты начала, а не хранится числом: иначе
    // «3 года» молча превращается в ложь через два года.
    cell: ({ row }) =>
      row.original.experience_years === null ||
      row.original.experience_years === undefined
        ? "Сведения не внесены"
        : `${row.original.experience_years} л.`,
  },
  {
    accessorKey: "license_due",
    header: "Удостоверение действительно",
    cell: ({ row }) =>
      dueCell(row.original.license_due, row.original.license_status_label),
  },
  {
    accessorKey: "status_label",
    header: "Допуск",
    cell: ({ row }) => row.original.status_label,
  },
];

/**
 * БДД: транспортные средства и водители (Доп. №1 разд. 56.2, срезы 1–2).
 *
 * До среза-1 по разд. 56.2 не было НИЧЕГО: ТЗ отсылало к «transport safety»,
 * которого в коде не существовало. Срез-2 добавил водителей — и человека НЕ
 * продублировал: карточка ссылается на ядрового сотрудника.
 */
const RoadSafetyPage = () => {
  // Секции ПО ОДНОЙ (прецедент экранов ПБ и ПромБеза): парк и водительский
  // состав — разные задачи, и показывать обе таблицы сразу значит растить
  // экран.
  const [section, setSection] = useState<"vehicles" | "drivers">("vehicles");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        vehicles: await roadSafetyApi.listVehicles(),
        drivers: await roadSafetyApi.listDrivers(),
        readiness: await roadSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      vehicles: [] as VehicleDto[],
      drivers: [] as DriverDto[],
      readiness: {
        total_vehicles: 0,
        by_status: { in_service: 0, suspended: 0, decommissioned: 0 },
        inspection_overdue: 0,
        insurance_overdue: 0,
        tachograph_overdue: 0,
        documents_missing: 0,
        total_drivers: 0,
        drivers_by_status: { admitted: 0, suspended: 0, dismissed: 0 },
        driver_license_overdue: 0,
        driver_license_missing: 0,
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

  const drivers = useLocalRegistry({
    items: data.drivers,
    match: (item, query) =>
      [
        item.person_name,
        item.license_number,
        item.categories.join(" "),
        item.status_label,
      ]
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
        description="Реестр транспортных средств и водительский состав: сроки диагностической карты, полиса, поверки тахографа и водительских удостоверений."
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
          { label: "Водителей", value: readiness.total_drivers },
          {
            label: "Допущено к управлению",
            value: readiness.drivers_by_status.admitted ?? 0,
          },
          // Тем же доводом: у отстранённого водителя просроченное
          // удостоверение это шум, а не проблема.
          {
            label: "Удостоверение просрочено",
            value: readiness.driver_license_overdue,
          },
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["vehicles", "Транспортные средства"],
            ["drivers", "Водители"],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            size="sm"
            variant={section === key ? "secondary" : "outline"}
            onClick={() => setSection(key)}
          >
            {label}
          </Button>
        ))}
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка парка" /> : null}

      {section === "drivers" ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ (прецедент тахографа и категории
            НВОС): какая категория нужна для конкретной машины и достаточен ли
            стаж для перевозки пассажиров, следует из массы ТС, числа мест и
            вида перевозок по закону — этих данных в системе нет.
          */}
          {!loading && !error ? (
            <p className="text-sm text-muted-foreground">
              Платформа ведёт внесённое и не решает, какая категория нужна для
              конкретной машины и хватает ли водителю стажа: это следует из
              массы ТС, числа мест и вида перевозок. Стаж считается от даты
              начала и не хранится числом — записанное «3 года» через два года
              стало бы неправдой. Просрочки считаются только по допущенным
              водителям.
            </p>
          ) : null}
          {!loading && !error && drivers.total === 0 ? (
            <EmptyState
              title="Водители не заведены"
              description="Заведите карточки водителей: сотрудник из справочника людей, номер удостоверения, категории и дата начала стажа. Отстранение меняет допуск в карточке, а не удаляет её."
            />
          ) : null}
          {!loading && !error && drivers.total > 0 ? (
            <RegistryTable
              columns={DRIVER_COLUMNS}
              data={drivers.pagedItems}
              pageIndex={drivers.pageIndex}
              pageSize={drivers.pageSize}
              total={drivers.total}
              onPageChange={drivers.onPageChange}
              onPageSizeChange={drivers.onPageSizeChange}
              onSearchChange={drivers.onSearchChange}
              searchPlaceholder="Поиск по фамилии, удостоверению, категории"
              caption="Водительский состав"
            />
          ) : null}
        </>
      ) : null}

      {section === "vehicles" ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ (прецедент категории НВОС и
            периодичности ПЭК): нужен ли тахограф и требуется ли лицензия,
            следует из вида перевозок, массы и категории ТС по закону — этих
            данных в системе нет.
          */}
          {!loading && !error ? (
            <p className="text-sm text-muted-foreground">
              Платформа ведёт учёт внесённого и не решает, нужен ли тахограф и
              требуется ли лицензия: это следует из вида перевозок, массы и
              категории ТС. Пустой срок означает «сведения не внесены», а не
              «бессрочно» — у полиса и диагностической карты бессрочности не
              бывает. Просрочки считаются только по машинам в эксплуатации.
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
        </>
      ) : null}
    </div>
  );
};

export default RoadSafetyPage;
