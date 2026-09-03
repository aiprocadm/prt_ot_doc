import { type ColumnDef } from "@tanstack/react-table";
import { useCallback, useState } from "react";

import {
  roadSafetyApi,
  type DriverDto,
  type RoadAccidentDto,
  type TrafficViolationDto,
  type RoadSafetyReadinessDto,
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
 * ДТП — РОВНО 7 колонок (лимит UX-бюджета, разд. 59.2). Вина и реквизиты
 * ГИБДД уехали в подсказки: их читают при разборе конкретного случая, а не
 * при просмотре списка.
 */
type Section = "vehicles" | "drivers" | "waybills" | "accidents" | "violations";

/**
 * Нарушения — 6 колонок (лимит UX-бюджета 7). Статья и место в подсказке:
 * их читают при разборе конкретного постановления, а не в списке.
 */
const VIOLATION_COLUMNS: ColumnDef<TrafficViolationDto, unknown>[] = [
  {
    accessorKey: "occurred_at",
    header: "Когда",
    cell: ({ row }) => formatDate(row.original.occurred_at),
  },
  { accessorKey: "vehicle_plate", header: "ТС" },
  {
    accessorKey: "driver_name",
    header: "Водитель",
    // Пусто — водитель НЕ УСТАНОВЛЕН (снято камерой), а не «неизвестно».
    cell: ({ row }) =>
      row.original.driver_identified
        ? row.original.driver_name
        : "Не установлен",
  },
  {
    accessorKey: "source_label",
    header: "Как выявлено",
    cell: ({ row }) => (
      <span title={row.original.article ?? ""}>{row.original.source_label}</span>
    ),
  },
  {
    accessorKey: "fine_amount",
    header: "Штраф",
    // Пусто — штраф НЕ НАЛОЖЕН, а не «сумма неизвестна».
    cell: ({ row }) =>
      row.original.fine_amount ? `${row.original.fine_amount} ₽` : "—",
  },
  {
    accessorKey: "fine_status_label",
    header: "Оплата",
    // Состояние СЧИТАЕТСЯ сервером из суммы и даты оплаты.
    cell: ({ row }) => row.original.fine_status_label,
  },
];

const ACCIDENT_COLUMNS: ColumnDef<RoadAccidentDto, unknown>[] = [
  {
    accessorKey: "occurred_at",
    header: "Когда",
    cell: ({ row }) => formatDate(row.original.occurred_at),
  },
  {
    accessorKey: "place",
    header: "Где",
    // Свободная строка, а не площадка: ДТП происходит на дороге.
    cell: ({ row }) => row.original.place,
  },
  {
    accessorKey: "vehicle_plate",
    header: "ТС",
    cell: ({ row }) => row.original.vehicle_plate,
  },
  {
    accessorKey: "driver_name",
    header: "Водитель",
    // Пусто — водителя за рулём НЕ БЫЛО (въехали в стоящую машину), а не
    // «неизвестно кто».
    cell: ({ row }) => row.original.driver_name ?? "За рулём никого не было",
  },
  {
    accessorKey: "kind_label",
    header: "Вид",
    cell: ({ row }) => (
      <span title={`Вина: ${row.original.fault_label}`}>
        {row.original.kind_label}
      </span>
    ),
  },
  {
    accessorKey: "consequences_label",
    header: "Последствия",
    // Тяжесть СЧИТАЕТСЯ сервером из чисел людей; числа — в подсказке.
    cell: ({ row }) => (
      <span
        title={`Пострадало: ${row.original.injured_count}; погибло: ${row.original.fatalities_count}`}
      >
        {row.original.consequences_label}
      </span>
    ),
  },
  {
    accessorKey: "follow_up_label",
    header: "Разбор",
    // Своего статуса «разобрано» у ДТП нет: состояние следует из ядровых
    // мероприятий и связи с расследованием.
    cell: ({ row }) => (
      <span title={`Мероприятий: ${row.original.capa_total}`}>
        {row.original.follow_up_label}
      </span>
    ),
  },
];

/**
 * Плитки шапки — ПО СЕКЦИЯМ, а не все сразу.
 *
 * ПОЧЕМУ ПЕРЕДЕЛАНО. К четвёртой секции общий набор дорос бы до пятнадцати
 * плиток, и человек, пришедший разбирать ДТП, первым делом читал бы про
 * поверку тахографов. ТЗ разд. 59 требует «одна задача — один экран», а
 * пятнадцать чисел о четырёх разных задачах — это ровно обратное. Теперь
 * каждая секция показывает СВОИ четыре числа.
 */
const SECTION_STATS: Record<
  Section,
  (r: RoadSafetyReadinessDto) => { label: string; value: number }[]
> = {
  vehicles: (r) => [
    { label: "Транспортных средств", value: r.total_vehicles },
    { label: "В эксплуатации", value: r.by_status.in_service ?? 0 },
    // Просрочки — ТОЛЬКО по эксплуатируемым: у списанной машины просроченный
    // полис это шум, а не проблема.
    { label: "Техосмотр просрочен", value: r.inspection_overdue },
    // ФАКТ о данных, а не вердикт о нарушении.
    { label: "Сведения не внесены", value: r.documents_missing },
  ],
  drivers: (r) => [
    { label: "Водителей", value: r.total_drivers },
    { label: "Допущено к управлению", value: r.drivers_by_status.admitted ?? 0 },
    // Тем же доводом: у отстранённого водителя просроченное удостоверение
    // это шум, а не проблема.
    { label: "Удостоверение просрочено", value: r.driver_license_overdue },
    // Срез-5: инструктажи водителей. Свой реестр не заводится — записи живут
    // в общем журнале инструктажей, здесь только счёт по видам БДД.
    { label: "Инструктаж БДД просрочен", value: r.road_briefings_overdue },
    // Срез-6: проверки знаний ПДД живут в общем реестре аттестаций.
    { label: "Проверка знаний просрочена", value: r.knowledge_checks_overdue },
    // Срез-7: стажировки. Показываем НЕДОБОР, а не общее число: формально
    // закрытая стажировка, которой по сменам не было, — вот что важно утром.
    {
      label: "Стажировка с недобором смен",
      value: r.internships_completed_short,
    },
  ],
  waybills: (r) => [
    {
      label: `Путевых листов за ${r.waybill_window_days} дн.`,
      value: r.waybills_total,
    },
    // Нарушение и дыра в учёте — РАЗНЫЕ числа, они не складываются.
    { label: "Контроль не пройден, листов", value: r.waybills_release_blocked },
    {
      label: "Контроль не подтверждён, листов",
      value: r.waybills_release_unconfirmed,
    },
    { label: "Аннулировано", value: r.waybills_by_status.cancelled ?? 0 },
  ],
  violations: (r) => [
    {
      label: `Нарушений за ${r.violation_window_days} дн.`,
      value: r.violations_total,
    },
    // Камера фиксирует машину, а не человека: платить есть кому, спросить
    // не с кого — именно ради этого числа водитель сделан необязательным.
    { label: "Водитель не установлен", value: r.violations_without_driver },
    { label: "Штрафов не оплачено", value: r.fines_unpaid_count },
    { label: "Долг по штрафам, ₽", value: r.fines_unpaid_amount },
  ],
  accidents: (r) => [
    // Окно ГОДОВОЕ: за месяц ДТП обычно ноль, и судить по нему нельзя.
    { label: `ДТП за ${r.accident_window_days} дн.`, value: r.accidents_total },
    // ФАКТЫ, а не оценка тяжести.
    { label: "Пострадало людей", value: r.injured_total },
    { label: "Погибло людей", value: r.fatalities_total },
    // Дыра в разборе, а не вердикт «разобрано плохо».
    { label: "Без разбора", value: r.accidents_without_follow_up },
  ],
};

/**
 * БДД: транспортные средства и водители (Доп. №1 разд. 56.2, срезы 1–2).
 *
 * До среза-1 по разд. 56.2 не было НИЧЕГО: ТЗ отсылало к «transport safety»,
 * которого в коде не существовало. Срез-2 добавил водителей — и человека НЕ
 * продублировал: карточка ссылается на ядрового сотрудника. Срез-3 добавил
 * путевые листы: они же журнал предрейсовых осмотров за период — отдельного
 * журнала не заводим, второй список тех же фактов разошёлся бы с первым.
 * Срез-4 добавил учёт ДТП со связью на ядровое расследование и мероприятия.
 */
const RoadSafetyPage = () => {
  // Секции ПО ОДНОЙ (прецедент экранов ПБ и ПромБеза): парк и водительский
  // состав — разные задачи, и показывать обе таблицы сразу значит растить
  // экран.
  const [section, setSection] = useState<Section>("vehicles");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        vehicles: await roadSafetyApi.listVehicles(),
        drivers: await roadSafetyApi.listDrivers(),
        waybills: await roadSafetyApi.listWaybills(),
        accidents: await roadSafetyApi.listAccidents(),
        violations: await roadSafetyApi.listViolations(),
        readiness: await roadSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      vehicles: [] as VehicleDto[],
      drivers: [] as DriverDto[],
      waybills: [] as WaybillDto[],
      accidents: [] as RoadAccidentDto[],
      violations: [] as TrafficViolationDto[],
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
        accident_window_days: 365,
        accidents_total: 0,
        accidents_by_consequences: { damage_only: 0, injured: 0, fatal: 0 },
        injured_total: 0,
        fatalities_total: 0,
        accidents_without_follow_up: 0,
        road_briefings_total: 0,
        road_briefings_overdue: 0,
        knowledge_checks_total: 0,
        knowledge_checks_overdue: 0,
        internships_total: 0,
        internships_in_progress: 0,
        internships_completed_short: 0,
        violation_window_days: 365,
        violations_total: 0,
        violations_without_driver: 0,
        fines_unpaid_count: 0,
        fines_unpaid_amount: 0,
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

  const accidents = useLocalRegistry({
    items: data.accidents,
    match: (item, query) =>
      [
        item.place,
        item.vehicle_plate,
        item.driver_name ?? "",
        item.kind_label,
        item.consequences_label,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const violations = useLocalRegistry({
    items: data.violations,
    match: (item, query) =>
      [
        item.vehicle_plate,
        item.driver_name ?? "",
        item.article ?? "",
        item.source_label,
        item.fine_status_label,
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
        stats={SECTION_STATS[section](readiness)}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["vehicles", "Транспортные средства"],
            ["drivers", "Водители"],
            ["waybills", "Путевые листы"],
            ["accidents", "ДТП"],
            ["violations", "Нарушения"],
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

      {section === "violations" ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: виновность устанавливает ГИБДД, а
            сроки обжалования и скидку платформа не считает.
          */}
          {!loading && !error ? (
            <p className="text-sm text-muted-foreground">
              Платформа ведёт учёт по постановлениям и не устанавливает
              виновность, не считает сроки обжалования и скидку за раннюю
              оплату. Водитель может быть не установлен — камера фиксирует
              госномер, а не человека, и штраф приходит собственнику: таких
              сейчас {readiness.violations_without_driver}. «Штраф не наложен»
              и «не оплачен» — разные вещи: замечание собственного контроля
              долгом не становится.
            </p>
          ) : null}
          {!loading && !error && violations.total === 0 ? (
            <EmptyState
              title="Нарушения не зарегистрированы"
              description="Внесите нарушение: машина из реестра, дата, как выявлено, статья и номер постановления. Водителя можно указать позже — его устанавливают уже после получения постановления."
            />
          ) : null}
          {!loading && !error && violations.total > 0 ? (
            <RegistryTable
              columns={VIOLATION_COLUMNS}
              data={violations.pagedItems}
              pageIndex={violations.pageIndex}
              pageSize={violations.pageSize}
              total={violations.total}
              onPageChange={violations.onPageChange}
              onPageSizeChange={violations.onPageSizeChange}
              onSearchChange={violations.onSearchChange}
              searchPlaceholder="Поиск по машине, водителю, статье"
              caption="Нарушения ПДД"
            />
          ) : null}
        </>
      ) : null}

      {section === "accidents" ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ (прецедент тахографа, стажа и
            выпуска): вину устанавливают ГИБДД и суд, а достаточность
            мероприятий платформа не оценивает.
          */}
          {!loading && !error ? (
            <p className="text-sm text-muted-foreground">
              Платформа ведёт учёт происшествий и не устанавливает вину — она
              следует из документов ГИБДД и решения суда, и вносится в запись
              как сведения. Расследование ведётся в общем контуре
              происшествий, мероприятия — в общем списке корректирующих
              действий: своих копий контур БДД не заводит. Поэтому «разбор»
              здесь не галочка, а следствие связей: без разбора сейчас{" "}
              {readiness.accidents_without_follow_up}. Тяжесть считается из
              числа пострадавших и погибших и словом не хранится.
            </p>
          ) : null}
          {!loading && !error && accidents.total === 0 ? (
            <EmptyState
              title="ДТП не зарегистрированы"
              description="Зарегистрируйте происшествие: когда и где, машина из реестра, вид ДТП и последствия. Водителя можно не указывать — в стоящую машину въезжают и без него. Если есть пострадавшие, свяжите запись с расследованием."
            />
          ) : null}
          {!loading && !error && accidents.total > 0 ? (
            <RegistryTable
              columns={ACCIDENT_COLUMNS}
              data={accidents.pagedItems}
              pageIndex={accidents.pageIndex}
              pageSize={accidents.pageSize}
              total={accidents.total}
              onPageChange={accidents.onPageChange}
              onPageSizeChange={accidents.onPageSizeChange}
              onSearchChange={accidents.onSearchChange}
              searchPlaceholder="Поиск по месту, машине, водителю, виду"
              caption="Учёт ДТП"
            />
          ) : null}
        </>
      ) : null}

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
              водителям. Инструктажи по БДД ведутся в общем журнале
              инструктажей — своего журнала контур не заводит; просрочено
              сейчас: {readiness.road_briefings_overdue} из{" "}
              {readiness.road_briefings_total}. Как часто инструктировать,
              платформа не решает: срок берётся из внесённого, а не из нормы.
              Проверки знаний ПДД так же ведутся в общем реестре аттестаций:
              просрочено {readiness.knowledge_checks_overdue} из{" "}
              {readiness.knowledge_checks_total}. Стажировки водителей ведутся
              общим механизмом стажировок — своего реестра контур не заводит:
              идёт {readiness.internships_in_progress} из{" "}
              {readiness.internships_total}. «Недобор смен» — расхождение
              плана и факта, а не приговор допуску: сколько смен нужно,
              решает приказ, а не платформа.
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
