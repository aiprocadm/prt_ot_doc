import { useCallback, useState } from "react";

import { ecologyApi } from "@/api/ecology";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { disciplineIncidentsStat } from "@/components/common/disciplineIncidentsStat";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

/**
 * Экология: реестр объектов НВОС (Доп. №1 разд. 55.1, срез-1).
 *
 * До этого экрана по экологии не было НИЧЕГО: ни сущностей, ни ручек, ни
 * страницы — дисциплина существовала словарной строкой, а весь контент
 * сводился к комплекту документов, где все значения вводятся руками.
 */
const EcologyPage = () => {
  // Секции ПО ОДНОЙ (прецедент экранов ПБ и ПромБеза): объекты, паспорта и
  // журнал учёта — разные задачи, три таблицы сразу растят экран.
  const [section, setSection] = useState<
    "facilities" | "waste" | "journal" | "emissions" | "pek" | "water" | "fee"
  >("facilities");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        facilities: await ecologyApi.listFacilities(),
        passports: await ecologyApi.listWastePassports(),
        movements: await ecologyApi.listWasteMovements(),
        sources: await ecologyApi.listEmissionSources(),
        norms: await ecologyApi.listEmissionNorms(),
        planItems: await ecologyApi.listMonitoringPlan(),
        measurements: await ecologyApi.listEmissionMeasurements(),
        waterPoints: await ecologyApi.listWaterPoints(),
        waterRecords: await ecologyApi.listWaterRecords(),
        feeRates: await ecologyApi.listFeeRates(),
        feeLines: await ecologyApi.listFeeLines(),
        readiness: await ecologyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      facilities: [],
      passports: [],
      movements: [],
      sources: [],
      norms: [],
      planItems: [],
      measurements: [],
      waterPoints: [],
      waterRecords: [],
      feeRates: [],
      feeLines: [],
      readiness: {
        incidents_open: 0,
        total_facilities: 0,
        by_category: { I: 0, II: 0, III: 0, IV: 0 },
        excluded_facilities: 0,
        never_actualized: 0,
        waste_passports: 0,
        waste_movements: 0,
        waste_over_limit: 0,
        emission_sources: 0,
        emission_sources_without_norms: 0,
        emission_norms: 0,
        emission_permits_overdue: 0,
        monitoring_plan_items: 0,
        monitoring_overdue: 0,
        measurements_this_year: 0,
        measurements_exceeded: 0,
        water_points: 0,
        water_permits_overdue: 0,
        water_intake_cubic_meters: "0.000",
        water_discharge_cubic_meters: "0.000",
        water_over_limit: 0,
        fee_lines: 0,
        fee_lines_without_rate: 0,
        fee_total_rubles: "0.00",
      },
    },
    errorMessage: "Не удалось загрузить реестр объектов НВОС",
  });

  const registry = useLocalRegistry({
    items: data.facilities,
    match: (item, query) =>
      [item.name, item.register_number, item.category_label, item.responsible]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const passportRegistry = useLocalRegistry({
    items: data.passports,
    match: (item, query) =>
      [item.name, item.fkko_code, item.hazard_class_label]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const movementRegistry = useLocalRegistry({
    items: data.movements,
    match: (item, query) =>
      [item.kind_label, item.counterparty, item.notes]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const sourceRegistry = useLocalRegistry({
    items: data.sources,
    match: (item, query) =>
      [item.name, item.source_number, item.kind_label, item.location]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const normRegistry = useLocalRegistry({
    items: data.norms,
    match: (item, query) =>
      [item.substance, item.permit_number]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const planRegistry = useLocalRegistry({
    items: data.planItems,
    match: (item, query) =>
      [item.substance, item.periodicity_label, item.laboratory, item.method]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const measurementRegistry = useLocalRegistry({
    items: data.measurements,
    match: (item, query) =>
      [item.substance, item.protocol_number, item.laboratory]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const waterPointRegistry = useLocalRegistry({
    items: data.waterPoints,
    match: (item, query) =>
      [item.name, item.point_number, item.kind_label, item.water_body]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const waterRecordRegistry = useLocalRegistry({
    items: data.waterRecords,
    match: (item, query) =>
      [item.period_label, item.basis_label, item.meter_number]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const feeRateRegistry = useLocalRegistry({
    items: data.feeRates,
    match: (item, query) =>
      [item.subject, item.impact_kind_label, item.source_document]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const feeLineRegistry = useLocalRegistry({
    items: data.feeLines,
    match: (item, query) =>
      [item.subject, item.impact_kind_label, item.rate_status_label]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const { readiness } = data;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Экология"
        description="Реестр объектов негативного воздействия на окружающую среду: постановка на государственный учёт, категория и актуализация сведений."
        stats={[
          { label: "Объектов на учёте", value: readiness.total_facilities },
          // От категории зависят и режим надзора, и состав отчётности.
          { label: "I категория", value: readiness.by_category.I ?? 0 },
          { label: "II категория", value: readiness.by_category.II ?? 0 },
          { label: "III категория", value: readiness.by_category.III ?? 0 },
          { label: "IV категория", value: readiness.by_category.IV ?? 0 },
          {
            label: "Снято с учёта",
            value: readiness.excluded_facilities,
          },
          // ФАКТ, а не нарушение: обязанность актуализировать сведения
          // возникает при изменении характеристик объекта, а не по календарю.
          {
            label: "Без актуализации сведений",
            value: readiness.never_actualized,
          },
          // Разд. 55.2 «отходы».
          { label: "Паспортов отходов", value: readiness.waste_passports },
          // ФАКТ по внесённым лимитам: платформа лимит не рассчитывает.
          {
            label: "Превышен лимит",
            value: readiness.waste_over_limit,
          },
          // Разд. 55.2 «выбросы».
          { label: "Источников выбросов", value: readiness.emission_sources },
          {
            label: "Разрешения просрочены",
            value: readiness.emission_permits_overdue,
          },
          // Разд. 55.2 «ПЭК». Превышение — ФАКТ сравнения замера с внесённым
          // нормативом, а не суждение платформы о самом нормативе.
          { label: "Замеры просрочены", value: readiness.monitoring_overdue },
          {
            label: "Превышений в замерах",
            value: readiness.measurements_exceeded,
          },
          // Разд. 55.2 «водопользование»: забор и сброс — РАЗНЫЕ величины,
          // в одну цифру их не складываем.
          { label: "Точек водопользования", value: readiness.water_points },
          // Разд. 55.3: плата за текущий год. Строки без ставки в итог не
          // попадают — про них отдельная цифра.
          {
            label: "Строк без ставки",
            value: readiness.fee_lines_without_rate,
          },
          // Доп. №1 разд. 57.4: происшествия контура — той же формулой, что
          // разрез у директора; ссылка ведёт в общий реестр (срез-49).
          disciplineIncidentsStat("ecology", readiness.incidents_open),
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["facilities", "Объекты НВОС"],
            ["waste", "Паспорта отходов"],
            ["journal", "Журнал учёта отходов"],
            ["emissions", "Выбросы"],
            ["pek", "ПЭК и замеры"],
            ["water", "Водопользование"],
            ["fee", "Плата за НВОС"],
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
      {loading ? <LoadingScreen label="Загрузка объектов НВОС" /> : null}
      {/*
        ГРАНИЦА, названная НА ЭКРАНЕ (прецедент интервала тренировок и
        требования ЭПБ): категорию объекта присваивают при постановке на
        государственный учёт по критериям постановления Правительства —
        мощность, виды воздействия, применяемые технологии. Этих данных в
        системе нет, поэтому платформа хранит внесённое, а не вычисляет.
      */}
      {section === "facilities" && !loading && !error ? (
        <p className="text-sm text-muted-foreground">
          Категория объекта присваивается при постановке на государственный учёт
          и хранится здесь как внесённая: платформа её не вычисляет — критерии
          опираются на мощность, виды воздействия и применяемые технологии,
          которых в системе нет.
        </p>
      ) : null}
      {section === "facilities" &&
      !loading &&
      !error &&
      registry.total === 0 ? (
        <EmptyState
          title="Объекты НВОС не заведены"
          description="Внесите объекты из свидетельства о постановке на государственный учёт: наименование, код объекта в реестре и категорию."
        />
      ) : null}
      {section === "facilities" && !loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "name", header: "Объект" },
            {
              accessorKey: "register_number",
              header: "Код в реестре",
              cell: ({ row }) => row.original.register_number,
            },
            {
              // Категория словами: код «II» человеку ничего не говорит.
              accessorKey: "category_label",
              header: "Категория",
              cell: ({ row }) => row.original.category_label,
            },
            {
              accessorKey: "registered_on",
              header: "На учёте с",
              cell: ({ row }) =>
                row.original.registered_on
                  ? formatDate(row.original.registered_on)
                  : "—",
            },
            {
              accessorKey: "actualized_on",
              header: "Сведения актуализированы",
              cell: ({ row }) =>
                row.original.actualized_on
                  ? formatDate(row.original.actualized_on)
                  : "не актуализировались",
            },
            {
              accessorKey: "status_label",
              header: "Состояние",
              cell: ({ row }) => row.original.status_label,
            },
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по объекту, коду, категории, ответственному"
          caption="Реестр объектов НВОС"
        />
      ) : null}
      {section === "waste" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: годовой лимит берётся из НООЛР или
            декларации — платформа его не рассчитывает, и без внесённого
            значения превышения быть не может по построению.
          */}
          <p className="text-sm text-muted-foreground">
            Паспорт составляется на отходы I–IV класса: отходы V класса
            паспортизации не подлежат. Годовой лимит вносится из документа
            (НООЛР или декларации) — платформа его не рассчитывает и без лимита
            о превышении не судит.
          </p>
          {passportRegistry.total === 0 ? (
            <EmptyState
              title="Паспорта отходов не заведены"
              description="Внесите паспорта по видам отходов: наименование, код ФККО, класс опасности и годовой лимит, если он установлен."
            />
          ) : (
            <RegistryTable
              columns={[
                { accessorKey: "name", header: "Вид отхода" },
                {
                  accessorKey: "fkko_code",
                  header: "Код ФККО",
                  cell: ({ row }) => row.original.fkko_code,
                },
                {
                  accessorKey: "hazard_class_label",
                  header: "Класс опасности",
                  cell: ({ row }) => row.original.hazard_class_label,
                },
                {
                  accessorKey: "generated_this_year_tons",
                  header: "Образование за год, т",
                  cell: ({ row }) => row.original.generated_this_year_tons,
                },
                {
                  accessorKey: "annual_limit_tons",
                  header: "Лимит, т",
                  cell: ({ row }) =>
                    row.original.annual_limit_tons
                      ? `${row.original.annual_limit_tons}${
                          row.original.over_limit ? " · превышен" : ""
                        }`
                      : "не установлен",
                },
              ]}
              data={passportRegistry.pagedItems}
              pageIndex={passportRegistry.pageIndex}
              pageSize={passportRegistry.pageSize}
              total={passportRegistry.total}
              onPageChange={passportRegistry.onPageChange}
              onPageSizeChange={passportRegistry.onPageSizeChange}
              onSearchChange={passportRegistry.onSearchChange}
              searchPlaceholder="Поиск по виду отхода, коду ФККО, классу"
              caption="Паспорта отходов"
            />
          )}
        </>
      ) : null}
      {section === "journal" && !loading && !error ? (
        <>
          {movementRegistry.total === 0 ? (
            <EmptyState
              title="Журнал учёта отходов пуст"
              description="Вносите движения по паспортам: образование, накопление, передачу оператору, размещение, обезвреживание и утилизацию."
            />
          ) : (
            <RegistryTable
              columns={[
                {
                  accessorKey: "happened_on",
                  header: "Дата",
                  cell: ({ row }) => formatDate(row.original.happened_on),
                },
                {
                  accessorKey: "kind_label",
                  header: "Движение",
                  cell: ({ row }) => row.original.kind_label,
                },
                {
                  accessorKey: "quantity_tons",
                  header: "Масса, т",
                  cell: ({ row }) => row.original.quantity_tons,
                },
                {
                  accessorKey: "counterparty",
                  header: "Контрагент",
                  cell: ({ row }) => row.original.counterparty || "—",
                },
                {
                  accessorKey: "contract_id",
                  header: "Договор",
                  cell: ({ row }) =>
                    row.original.contract_id ? "по договору" : "—",
                },
              ]}
              data={movementRegistry.pagedItems}
              pageIndex={movementRegistry.pageIndex}
              pageSize={movementRegistry.pageSize}
              total={movementRegistry.total}
              onPageChange={movementRegistry.onPageChange}
              onPageSizeChange={movementRegistry.onPageSizeChange}
              onSearchChange={movementRegistry.onSearchChange}
              searchPlaceholder="Поиск по движению и контрагенту"
              caption="Журнал учёта отходов"
            />
          )}
        </>
      ) : null}
      {section === "emissions" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: норматив (ПДВ) устанавливается
            расчётом рассеивания в проекте нормативов и утверждается
            разрешением — платформа его не рассчитывает и по нему не судит.
          */}
          <p className="text-sm text-muted-foreground">
            Нормативы выброса устанавливаются проектом нормативов и утверждаются
            разрешением: платформа их не рассчитывает и хранит как внесённые.
            Пустой срок разрешения означает «бессрочно», а не «просрочено».
          </p>
          {sourceRegistry.total === 0 ? (
            <EmptyState
              title="Источники выбросов не заведены"
              description="Внесите стационарные источники по инвентаризации: номер, наименование и тип — организованный (труба, аэрационный фонарь) или неорганизованный."
            />
          ) : (
            <RegistryTable
              columns={[
                { accessorKey: "source_number", header: "№ источника" },
                { accessorKey: "name", header: "Наименование" },
                {
                  accessorKey: "kind_label",
                  header: "Тип",
                  cell: ({ row }) => row.original.kind_label,
                },
                {
                  accessorKey: "location",
                  header: "Место",
                  cell: ({ row }) => row.original.location || "—",
                },
                {
                  accessorKey: "inventoried_on",
                  header: "Инвентаризация",
                  cell: ({ row }) =>
                    row.original.inventoried_on
                      ? formatDate(row.original.inventoried_on)
                      : "не проводилась",
                },
                {
                  accessorKey: "norms_count",
                  header: "Нормативов",
                  cell: ({ row }) =>
                    row.original.norms_count > 0
                      ? `${row.original.norms_count}`
                      : "нет",
                },
              ]}
              data={sourceRegistry.pagedItems}
              pageIndex={sourceRegistry.pageIndex}
              pageSize={sourceRegistry.pageSize}
              total={sourceRegistry.total}
              onPageChange={sourceRegistry.onPageChange}
              onPageSizeChange={sourceRegistry.onPageSizeChange}
              onSearchChange={sourceRegistry.onSearchChange}
              searchPlaceholder="Поиск по номеру, наименованию, типу"
              caption="Инвентаризация источников выбросов"
            />
          )}
          {normRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "substance", header: "Вещество" },
                {
                  accessorKey: "limit_grams_per_second",
                  header: "ПДВ, г/с",
                  cell: ({ row }) => row.original.limit_grams_per_second ?? "—",
                },
                {
                  accessorKey: "limit_tons_per_year",
                  header: "ПДВ, т/год",
                  cell: ({ row }) => row.original.limit_tons_per_year ?? "—",
                },
                {
                  accessorKey: "valid_until",
                  header: "Разрешение до",
                  cell: ({ row }) =>
                    row.original.valid_until
                      ? formatDate(row.original.valid_until)
                      : "бессрочно",
                },
                {
                  accessorKey: "validity_status_label",
                  header: "Состояние",
                  cell: ({ row }) => row.original.validity_status_label,
                },
              ]}
              data={normRegistry.pagedItems}
              pageIndex={normRegistry.pageIndex}
              pageSize={normRegistry.pageSize}
              total={normRegistry.total}
              onPageChange={normRegistry.onPageChange}
              onPageSizeChange={normRegistry.onPageSizeChange}
              onSearchChange={normRegistry.onSearchChange}
              searchPlaceholder="Поиск по веществу и номеру разрешения"
              caption="Нормативы выбросов по веществам"
            />
          ) : null}
        </>
      ) : null}
      {section === "pek" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: периодичность замеров берётся из
            утверждённой программы ПЭК — платформа её не назначает. А вот
            превышение здесь считается: это сравнение замера с внесённым
            нормативом, то есть факт по двум числам.
          */}
          <p className="text-sm text-muted-foreground">
            Периодичность замеров берётся из утверждённой программы ПЭК:
            платформа её не назначает. Превышение показывается только там, где
            внесён разовый норматив в г/с — без норматива сравнивать не с чем.
          </p>
          {planRegistry.total === 0 ? (
            <EmptyState
              title="План-график замеров не заведён"
              description="Внесите строки графика по программе ПЭК: вещество на источнике, периодичность в месяцах и дату ближайшего замера."
            />
          ) : (
            <RegistryTable
              columns={[
                { accessorKey: "substance", header: "Вещество" },
                {
                  accessorKey: "periodicity_label",
                  header: "Периодичность",
                  cell: ({ row }) => row.original.periodicity_label,
                },
                {
                  accessorKey: "next_due_on",
                  header: "Ближайший замер",
                  cell: ({ row }) => formatDate(row.original.next_due_on),
                },
                {
                  accessorKey: "status_label",
                  header: "Состояние",
                  cell: ({ row }) => row.original.status_label,
                },
                {
                  accessorKey: "last_measured_on",
                  header: "Последний замер",
                  cell: ({ row }) =>
                    row.original.last_measured_on
                      ? formatDate(row.original.last_measured_on)
                      : "замеров не было",
                },
                {
                  accessorKey: "laboratory",
                  header: "Лаборатория",
                  cell: ({ row }) => row.original.laboratory || "—",
                },
              ]}
              data={planRegistry.pagedItems}
              pageIndex={planRegistry.pageIndex}
              pageSize={planRegistry.pageSize}
              total={planRegistry.total}
              onPageChange={planRegistry.onPageChange}
              onPageSizeChange={planRegistry.onPageSizeChange}
              onSearchChange={planRegistry.onSearchChange}
              searchPlaceholder="Поиск по веществу, периодичности, лаборатории"
              caption="План-график замеров ПЭК"
            />
          )}
          {measurementRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                {
                  accessorKey: "measured_on",
                  header: "Дата замера",
                  cell: ({ row }) => formatDate(row.original.measured_on),
                },
                { accessorKey: "substance", header: "Вещество" },
                {
                  accessorKey: "value_grams_per_second",
                  header: "Замер, г/с",
                },
                {
                  accessorKey: "norm_grams_per_second",
                  header: "Норматив, г/с",
                  cell: ({ row }) => row.original.norm_grams_per_second ?? "—",
                },
                {
                  accessorKey: "comparison_label",
                  header: "Итог",
                  cell: ({ row }) => row.original.comparison_label,
                },
                {
                  accessorKey: "protocol_number",
                  header: "Протокол",
                  cell: ({ row }) => row.original.protocol_number || "—",
                },
              ]}
              data={measurementRegistry.pagedItems}
              pageIndex={measurementRegistry.pageIndex}
              pageSize={measurementRegistry.pageSize}
              total={measurementRegistry.total}
              onPageChange={measurementRegistry.onPageChange}
              onPageSizeChange={measurementRegistry.onPageSizeChange}
              onSearchChange={measurementRegistry.onSearchChange}
              searchPlaceholder="Поиск по веществу и номеру протокола"
              caption="Замеры ПЭК"
            />
          ) : null}
        </>
      ) : null}
      {section === "water" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: нужно ли разрешение (договор
            водопользования, решение о предоставлении водного объекта) и каков
            норматив допустимого сброса — устанавливает орган. Платформа
            хранит внесённое и складывает объёмы.
          */}
          <p className="text-sm text-muted-foreground">
            Забор и сброс считаются раздельно: это разные величины. Нужно ли
            разрешение и каков норматив сброса, определяет орган — платформа
            хранит внесённое. Превышение показывается только там, где внесён
            годовой лимит.
          </p>
          <p className="text-sm">
            Забор за год: {readiness.water_intake_cubic_meters} м³ · сброс за
            год: {readiness.water_discharge_cubic_meters} м³
          </p>
          {waterPointRegistry.total === 0 ? (
            <EmptyState
              title="Точки водопользования не заведены"
              description="Внесите водозаборы и выпуски сточных вод: номер точки, водный объект, реквизиты разрешения и годовой лимит, если он установлен."
            />
          ) : (
            <RegistryTable
              columns={[
                { accessorKey: "point_number", header: "№ точки" },
                { accessorKey: "name", header: "Наименование" },
                {
                  accessorKey: "kind_label",
                  header: "Тип",
                  cell: ({ row }) => row.original.kind_label,
                },
                {
                  accessorKey: "water_body",
                  header: "Водный объект",
                  cell: ({ row }) => row.original.water_body || "не указан",
                },
                {
                  accessorKey: "permit_valid_until",
                  header: "Разрешение до",
                  cell: ({ row }) =>
                    row.original.permit_valid_until
                      ? formatDate(row.original.permit_valid_until)
                      : "бессрочно",
                },
                {
                  accessorKey: "volume_this_year",
                  header: "Объём за год, м³",
                  cell: ({ row }) =>
                    row.original.over_limit
                      ? `${row.original.volume_this_year} — превышен лимит`
                      : row.original.volume_this_year,
                },
              ]}
              data={waterPointRegistry.pagedItems}
              pageIndex={waterPointRegistry.pageIndex}
              pageSize={waterPointRegistry.pageSize}
              total={waterPointRegistry.total}
              onPageChange={waterPointRegistry.onPageChange}
              onPageSizeChange={waterPointRegistry.onPageSizeChange}
              onSearchChange={waterPointRegistry.onSearchChange}
              searchPlaceholder="Поиск по номеру, наименованию, водному объекту"
              caption="Точки водопользования"
            />
          )}
          {waterRecordRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "period_label", header: "Период" },
                {
                  accessorKey: "volume_cubic_meters",
                  header: "Объём, м³",
                },
                {
                  accessorKey: "basis_label",
                  header: "Основание",
                  cell: ({ row }) => row.original.basis_label,
                },
                {
                  accessorKey: "meter_number",
                  header: "Прибор учёта",
                  cell: ({ row }) => row.original.meter_number || "—",
                },
              ]}
              data={waterRecordRegistry.pagedItems}
              pageIndex={waterRecordRegistry.pageIndex}
              pageSize={waterRecordRegistry.pageSize}
              total={waterRecordRegistry.total}
              onPageChange={waterRecordRegistry.onPageChange}
              onPageSizeChange={waterRecordRegistry.onPageSizeChange}
              onSearchChange={waterRecordRegistry.onSearchChange}
              searchPlaceholder="Поиск по периоду, основанию, прибору"
              caption="Помесячный учёт объёмов"
            />
          ) : null}
        </>
      ) : null}
      {section === "fee" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: ставки устанавливает Правительство и
            меняет ежегодно, коэффициенты определяются законом и решением
            органа. Платформа умножает внесённое, а не догадывается.
          */}
          <p className="text-sm text-muted-foreground">
            Ставки и коэффициенты вносятся: ставку устанавливает Правительство
            ежегодно, а повышающий коэффициент определяют закон и решение
            органа. Платформа перемножает внесённое. Если ставки за нужный год
            нет, сумма не считается вовсе — это не ноль.
          </p>
          <p className="text-sm">
            Плата за {new Date().getFullYear()} год по посчитанным строкам:{" "}
            {readiness.fee_total_rubles} ₽
          </p>
          {feeLineRegistry.total === 0 ? (
            <EmptyState
              title="Расчёт платы не заведён"
              description="Внесите строки расчёта по кварталам: вид воздействия, вещество или класс отходов, массу за квартал и коэффициент. Кварталы — это и есть авансовые платежи."
            />
          ) : (
            <RegistryTable
              columns={[
                {
                  accessorKey: "quarter",
                  header: "Период",
                  cell: ({ row }) =>
                    `${row.original.quarter} кв. ${row.original.year}`,
                },
                {
                  accessorKey: "impact_kind_label",
                  header: "Вид воздействия",
                  cell: ({ row }) => row.original.impact_kind_label,
                },
                { accessorKey: "subject", header: "Вещество / отход" },
                { accessorKey: "mass_tons", header: "Масса, т" },
                { accessorKey: "coefficient", header: "Коэффициент" },
                {
                  accessorKey: "amount_rubles",
                  header: "Сумма, ₽",
                  cell: ({ row }) =>
                    row.original.amount_rubles ??
                    row.original.rate_status_label,
                },
              ]}
              data={feeLineRegistry.pagedItems}
              pageIndex={feeLineRegistry.pageIndex}
              pageSize={feeLineRegistry.pageSize}
              total={feeLineRegistry.total}
              onPageChange={feeLineRegistry.onPageChange}
              onPageSizeChange={feeLineRegistry.onPageSizeChange}
              onSearchChange={feeLineRegistry.onSearchChange}
              searchPlaceholder="Поиск по веществу и виду воздействия"
              caption="Расчёт платы по кварталам"
            />
          )}
          {feeRateRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "year", header: "Год" },
                {
                  accessorKey: "impact_kind_label",
                  header: "Вид воздействия",
                  cell: ({ row }) => row.original.impact_kind_label,
                },
                { accessorKey: "subject", header: "Вещество / отход" },
                { accessorKey: "rate_per_ton", header: "Ставка, ₽/т" },
                {
                  accessorKey: "source_document",
                  header: "Чем установлена",
                  cell: ({ row }) =>
                    row.original.source_document || "не указано",
                },
              ]}
              data={feeRateRegistry.pagedItems}
              pageIndex={feeRateRegistry.pageIndex}
              pageSize={feeRateRegistry.pageSize}
              total={feeRateRegistry.total}
              onPageChange={feeRateRegistry.onPageChange}
              onPageSizeChange={feeRateRegistry.onPageSizeChange}
              onSearchChange={feeRateRegistry.onSearchChange}
              searchPlaceholder="Поиск по веществу и постановлению"
              caption="Справочник ставок платы"
            />
          ) : null}
        </>
      ) : null}
    </div>
  );
};

export default EcologyPage;
