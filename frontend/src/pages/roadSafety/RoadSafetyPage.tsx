import { type ColumnDef } from "@tanstack/react-table";
import { useCallback, useState } from "react";

import {
  roadSafetyApi,
  type DriverDto,
  type VehicleDto,
  type WaybillDto,
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
 * Путевые листы — РОВНО 7 колонок: столько разрешает UX-бюджет (разд. 59.2).
 * Послерейсовый осмотр уехал в подсказку к предрейсовому, а не в восьмую
 * колонку: он обязателен не всем, и держать его наравне с обязательными
 * значило бы уравнять разное.
 */
const WAYBILL_COLUMNS: ColumnDef<WaybillDto, unknown>[] = [
  { accessorKey: "number", header: "Номер" },
  {
    accessorKey: "issued_on",
    header: "Дата и рейс",
    // Время В РЕЙСЕ, а не за рулём: сколько из рейса человек реально вёл
    // машину, платформа не знает. Пусто — сведений о выезде нет, а не «ноль».
    cell: ({ row }) =>
      row.original.trip_hours === null || row.original.trip_hours === undefined
        ? formatDate(row.original.issued_on)
        : `${formatDate(row.original.issued_on)} · ${row.original.trip_hours} ч в рейсе`,
  },
  {
    accessorKey: "vehicle_plate",
    header: "ТС",
    // Госномер приходит из реестра ТС: в листе он не хранится, иначе смена
    // номера оставила бы старый в тысяче листов.
    cell: ({ row }) => (
      <span title={row.original.vehicle_brand_model}>
        {row.original.vehicle_plate}
      </span>
    ),
  },
  { accessorKey: "driver_name", header: "Водитель" },
  {
    accessorKey: "pre_trip_medical_label",
    header: "Медосмотр",
    cell: ({ row }) => (
      <span
        title={`Послерейсовый: ${row.original.post_trip_medical_label}`}
      >
        {row.original.pre_trip_medical_label}
      </span>
    ),
  },
  {
    accessorKey: "pre_trip_technical_label",
    header: "Техконтроль",
    cell: ({ row }) => row.original.pre_trip_technical_label,
  },
  {
    accessorKey: "release_status_label",
    header: "Выпуск",
    // Вердикт СЧИТАЕТСЯ сервером из двух обязательных отметок и не хранится:
    // сохранённый разошёлся бы с отметками при первой правке.
    cell: ({ row }) => row.original.release_status_label,
  },
];

/**
 * БДД: транспортные средства и водители (Доп. №1 разд. 56.2, срезы 1–2).
 *
 * До среза-1 по разд. 56.2 не было НИЧЕГО: ТЗ отсылало к «transport safety»,
 * которого в коде не существовало. Срез-2 добавил водителей — и человека НЕ
 * продублировал: карточка ссылается на ядрового сотрудника. Срез-3 добавил
 * путевые листы: они же журнал предрейсовых осмотров за период — отдельного
 * журнала не заводим, второй список тех же фактов разошёлся бы с первым.
 */
const RoadSafetyPage = () => {
  // Секции ПО ОДНОЙ (прецедент экранов ПБ и ПромБеза): парк и водительский
  // состав — разные задачи, и показывать обе таблицы сразу значит растить
  // экран.
  const [section, setSection] = useState<"vehicles" | "drivers" | "waybills">(
    "vehicles",
  );

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        vehicles: await roadSafetyApi.listVehicles(),
        drivers: await roadSafetyApi.listDrivers(),
        waybills: await roadSafetyApi.listWaybills(),
        readiness: await roadSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      vehicles: [] as VehicleDto[],
      drivers: [] as DriverDto[],
      waybills: [] as WaybillDto[],
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
        waybill_window_days: 30,
        waybills_total: 0,
        waybills_by_status: { issued: 0, closed: 0, cancelled: 0 },
        waybills_release_blocked: 0,
        waybills_release_unconfirmed: 0,
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

  const waybills = useLocalRegistry({
    items: data.waybills,
    match: (item, query) =>
      [
        item.number,
        item.vehicle_plate,
        item.driver_name,
        item.release_status_label,
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
        description="Реестр транспортных средств, водительский состав и путевые листы: сроки диагностической карты, полиса, поверки тахографа, водительских удостоверений и отметки контроля перед выездом."
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
          // Срез-3: листы считаются ЗА ОКНО, а не за всё время — реестр
          // растёт каждую смену, и «всего за три года» ни о чём не говорит.
          {
            label: `Путевых листов за ${readiness.waybill_window_days} дн.`,
            value: readiness.waybills_total,
          },
          // Нарушение и дыра в учёте — РАЗНЫЕ числа: «не пройден» здесь,
          // «сведения не внесены» отдельной подписью в секции листов.
          //
          // ПОДПИСЬ НЕ ПОВТОРЯЕТ ВЕРДИКТ СТРОКИ дословно: плитка считает
          // ЛИСТЫ, а вердикт в таблице говорит о ЭТОМ листе. Совпади они
          // слово в слово — на экране появились бы две одинаковые надписи о
          // разном, и понять, к чему относится число, стало бы нельзя.
          {
            label: "Контроль не пройден, листов",
            value: readiness.waybills_release_blocked,
          },
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["vehicles", "Транспортные средства"],
            ["drivers", "Водители"],
            ["waybills", "Путевые листы"],
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

      {section === "waybills" ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ (прецедент тахографа и стажа):
            платформа не решает, законен ли выпуск и уложился ли водитель в
            режим труда и отдыха — это следует из вида перевозок и
            суммирования за неделю, а этих данных в системе нет.
          */}
          {!loading && !error ? (
            <p className="text-sm text-muted-foreground">
              Реестр листов с отбором по датам и есть журнал предрейсовых
              осмотров — отдельного журнала платформа не ведёт. Выпуск
              подтверждается двумя отметками: предрейсовым медосмотром и
              техконтролем; послерейсовый осмотр в вердикт не входит, потому
              что обязателен не всем. «Сведения не внесены» и «не пройден» —
              разные вещи: первое дыра в учёте, второе нарушение выпуска.
              Сейчас без подтверждения контроля: {" "}
              {readiness.waybills_release_unconfirmed}. Время считается в
              рейсе, а не за рулём, и платформа не судит о превышении.
            </p>
          ) : null}
          {!loading && !error && waybills.total === 0 ? (
            <EmptyState
              title="Путевые листы не выписаны"
              description="Выпишите лист: номер, машина из реестра ТС, допущенный водитель и дата. Отметки предрейсового медосмотра и техконтроля ставятся в самом листе. Ошибочный лист аннулируется, а не удаляется."
            />
          ) : null}
          {!loading && !error && waybills.total > 0 ? (
            <RegistryTable
              columns={WAYBILL_COLUMNS}
              data={waybills.pagedItems}
              pageIndex={waybills.pageIndex}
              pageSize={waybills.pageSize}
              total={waybills.total}
              onPageChange={waybills.onPageChange}
              onPageSizeChange={waybills.onPageSizeChange}
              onSearchChange={waybills.onSearchChange}
              searchPlaceholder="Поиск по номеру, машине, водителю"
              caption="Путевые листы"
            />
          ) : null}
        </>
      ) : null}

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
