import { useCallback, useState } from "react";

import {
  industrialSafetyApi,
  OPO_WORK_RESULT_TITLES,
} from "@/api/industrialSafety";
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
 * Промышленная безопасность: реестр ОПО и технические устройства
 * (Доп. №1 разд. 54.2, срезы 1–2).
 *
 * До этого экрана «ОПО» существовало тремя полями площадки, причём класс
 * опасности был свободной строкой, в которую клали и класс ОПО («II»), и
 * категорию пожарной опасности («В2»). Считать по классам было нечего, а
 * несколько объектов на одной площадке полями площадки не выражаются вовсе.
 *
 * Устройства — вторая секция: ядровые Asset/Equipment это две и три колонки
 * без ручек API и без единого поля срока, учитывать по ним экспертизу нечем.
 */
const IndustrialSafetyPage = () => {
  // Секции ПО ОДНОЙ (прецедент экрана ПБ): объекты и устройства — разные
  // задачи, и показывать обе таблицы сразу значит растить экран.
  const [section, setSection] = useState<"facilities" | "devices">(
    "facilities",
  );

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        facilities: await industrialSafetyApi.listFacilities(),
        devices: await industrialSafetyApi.listDevices(),
        readiness: await industrialSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      facilities: [],
      devices: [],
      readiness: {
        total_facilities: 0,
        by_class: { I: 0, II: 0, III: 0, IV: 0 },
        excluded_facilities: 0,
        total_devices: 0,
        epb_overdue: 0,
        epb_due_soon: 0,
        devices_past_lifetime_without_epb: 0,
        devices_without_work_record: 0,
      },
    },
    errorMessage: "Не удалось загрузить реестр ОПО",
  });

  const registry = useLocalRegistry({
    items: data.facilities,
    match: (item, query) =>
      [
        item.name,
        item.register_number,
        item.hazard_class_label,
        item.responsible,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const deviceRegistry = useLocalRegistry({
    items: data.devices,
    match: (item, query) =>
      [
        item.name,
        item.kind_label,
        item.serial_number,
        item.epb_conclusion_number,
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
        title="Промышленная безопасность"
        description="Реестр опасных производственных объектов и технических устройств: регистрационные сведения, класс опасности и экспертиза промышленной безопасности."
        stats={[
          { label: "Действующих ОПО", value: readiness.total_facilities },
          // I и II класс — постоянный государственный надзор и обязательная
          // декларация промышленной безопасности, поэтому они названы отдельно.
          { label: "I класс", value: readiness.by_class.I ?? 0 },
          { label: "II класс", value: readiness.by_class.II ?? 0 },
          {
            label: "Исключено из реестра",
            value: readiness.excluded_facilities,
          },
          { label: "Устройств в работе", value: readiness.total_devices },
          { label: "Просрочено ЭПБ", value: readiness.epb_overdue },
          // ФАКТ, а не обвинение: срок службы истёк и действующего заключения
          // нет. Нужна ли экспертиза именно этому устройству — решает
          // специалист (см. подпись секции устройств).
          {
            label: "Отработали срок без ЭПБ",
            value: readiness.devices_past_lifetime_without_epb,
          },
          // Разд. 54.2 «история работ»: срок без единой записи о работах —
          // обещание, а не доказательство.
          {
            label: "Без записей о работах",
            value: readiness.devices_without_work_record,
          },
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["facilities", "Объекты (ОПО)"],
            ["devices", "Технические устройства"],
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
      {loading ? <LoadingScreen label="Загрузка реестра ОПО" /> : null}
      {section === "devices" ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ (прецедент интервала тренировок):
            платформа не решает, нужна ли устройству экспертиза — это зависит
            от типа устройства, наличия документации и норм ФНП, которых в
            данных нет. Показываем факты: срок службы истёк, заключение
            просрочено или его нет.
          */}
          {!loading && !error ? (
            <p className="text-sm text-muted-foreground">
              Состояние экспертизы считается по внесённым вами сведениям:
              назначенному сроку службы и сроку из заключения ЭПБ. Нужна ли
              экспертиза конкретному устройству, определяет специалист —
              требование зависит от типа устройства и норм ФНП.
            </p>
          ) : null}
          {!loading && !error && deviceRegistry.total === 0 ? (
            <EmptyState
              title="Технические устройства не заведены"
              description="Внесите устройства, эксплуатируемые на объекте: тип, заводской номер, назначенный срок службы и заключение экспертизы промышленной безопасности."
            />
          ) : null}
          {!loading && !error && deviceRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "name", header: "Устройство" },
                {
                  accessorKey: "kind_label",
                  header: "Тип",
                  cell: ({ row }) => row.original.kind_label,
                },
                {
                  accessorKey: "serial_number",
                  header: "Зав. номер",
                  cell: ({ row }) => row.original.serial_number || "—",
                },
                {
                  accessorKey: "lifetime_until",
                  header: "Срок службы",
                  cell: ({ row }) =>
                    row.original.lifetime_until
                      ? `${formatDate(row.original.lifetime_until)}${
                          row.original.past_lifetime ? " · истёк" : ""
                        }`
                      : "не указан",
                },
                {
                  accessorKey: "epb_valid_until",
                  header: "ЭПБ до",
                  cell: ({ row }) =>
                    row.original.epb_valid_until
                      ? formatDate(row.original.epb_valid_until)
                      : "—",
                },
                {
                  accessorKey: "epb_status_label",
                  header: "Экспертиза",
                  cell: ({ row }) => row.original.epb_status_label,
                },
                {
                  // Разд. 54.2 «история работ»: последняя ПОДТВЕРЖДЁННАЯ
                  // работа. Отсутствие записей названо словами — пустая ячейка
                  // читалась бы как «данные не подгрузились».
                  accessorKey: "last_work_on",
                  header: "Последняя работа",
                  cell: ({ row }) =>
                    row.original.last_work_on
                      ? `${formatDate(row.original.last_work_on)} · ${
                          OPO_WORK_RESULT_TITLES[
                            row.original.last_work_result ?? ""
                          ] ?? "—"
                        }`
                      : "нет записей",
                },
              ]}
              data={deviceRegistry.pagedItems}
              pageIndex={deviceRegistry.pageIndex}
              pageSize={deviceRegistry.pageSize}
              total={deviceRegistry.total}
              onPageChange={deviceRegistry.onPageChange}
              onPageSizeChange={deviceRegistry.onPageSizeChange}
              onSearchChange={deviceRegistry.onSearchChange}
              searchPlaceholder="Поиск по названию, типу, номеру, заключению"
              caption="Технические устройства на ОПО"
            />
          ) : null}
        </>
      ) : null}
      {section === "facilities" &&
      !loading &&
      !error &&
      registry.total === 0 ? (
        <EmptyState
          title="Опасные производственные объекты не заведены"
          description="Внесите объекты из свидетельства о регистрации: наименование, регистрационный номер и класс опасности. На одной площадке объектов может быть несколько."
        />
      ) : null}
      {section === "facilities" && !loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { accessorKey: "name", header: "Объект" },
            {
              accessorKey: "register_number",
              header: "Рег. номер",
              cell: ({ row }) => row.original.register_number,
            },
            {
              // Подпись готовит сервер: код «III» человеку ничего не говорит.
              accessorKey: "hazard_class_label",
              header: "Класс опасности",
              cell: ({ row }) => row.original.hazard_class_label,
            },
            {
              accessorKey: "registered_on",
              header: "Зарегистрирован",
              cell: ({ row }) =>
                row.original.registered_on
                  ? formatDate(row.original.registered_on)
                  : "—",
            },
            {
              accessorKey: "status_label",
              header: "Состояние",
              cell: ({ row }) => row.original.status_label,
            },
            {
              accessorKey: "responsible",
              header: "Ответственный",
              cell: ({ row }) => row.original.responsible || "—",
            },
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по названию, номеру, классу, ответственному"
          caption="Реестр опасных производственных объектов"
        />
      ) : null}
    </div>
  );
};

export default IndustrialSafetyPage;
