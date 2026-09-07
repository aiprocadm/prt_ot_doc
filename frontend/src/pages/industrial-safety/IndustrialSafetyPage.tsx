import { useCallback, useState } from "react";

import {
  industrialSafetyApi,
  OPO_WORK_RESULT_TITLES,
} from "@/api/industrialSafety";
import { sitesApi } from "@/api/sites";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { disciplineIncidentsStat } from "@/components/common/disciplineIncidentsStat";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { OpoDeviceFormDialog } from "@/features/industrial-safety/OpoDeviceFormDialog";
import { OpoDeviceWorkFormDialog } from "@/features/industrial-safety/OpoDeviceWorkFormDialog";
import { OpoFacilityFormDialog } from "@/features/industrial-safety/OpoFacilityFormDialog";
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
  const [section, setSection] = useState<
    "facilities" | "devices" | "attestations" | "control"
  >("facilities");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        facilities: await industrialSafetyApi.listFacilities(),
        // Площадки — ядровой справочник: объект привязывают выбором,
        // а не вводом id (срез-105).
        sites: (await sitesApi.list()).items,
        devices: await industrialSafetyApi.listDevices(),
        attestations: await industrialSafetyApi.listAttestations(),
        pcMeasures: await industrialSafetyApi.listPcMeasures(),
        readiness: await industrialSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      facilities: [],
      sites: [],
      devices: [],
      attestations: [],
      pcMeasures: [],
      readiness: {
        incidents_open: 0,
        total_facilities: 0,
        by_class: { I: 0, II: 0, III: 0, IV: 0 },
        excluded_facilities: 0,
        total_devices: 0,
        epb_overdue: 0,
        epb_due_soon: 0,
        devices_past_lifetime_without_epb: 0,
        devices_without_work_record: 0,
        attestations_total: 0,
        attestations_overdue: 0,
        attestations_due_soon: 0,
        current_year_plan_exists: false,
        pc_measures_overdue: 0,
        pc_measures_planned: 0,
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

  const attestationRegistry = useLocalRegistry({
    items: data.attestations,
    match: (item, query) =>
      [item.person_name, item.area_label, item.name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const measureRegistry = useLocalRegistry({
    items: data.pcMeasures,
    match: (item, query) =>
      [item.title, item.section_label, item.responsible]
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
          // Разд. 54.2 «аттестация персонала»: просроченная аттестация — это
          // нарушение допуска человека к работам на ОПО.
          {
            label: "Просрочено аттестаций",
            value: readiness.attestations_overdue,
          },
          // Разд. 54.2 «производственный контроль»: просроченное мероприятие
          // плана — это невыполненный план, который предъявляется надзору.
          {
            label: "Просрочено мероприятий ПК",
            value: readiness.pc_measures_overdue,
          },
          // Доп. №1 разд. 57.4: происшествия контура — той же формулой, что
          // разрез у директора; ссылка ведёт в общий реестр (срез-49).
          disciplineIncidentsStat(
            "industrial_safety",
            readiness.incidents_open,
          ),
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["facilities", "Объекты (ОПО)"],
            ["devices", "Технические устройства"],
            ["attestations", "Аттестация персонала"],
            ["control", "Производственный контроль"],
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
      {section === "control" ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: платформа сообщает ФАКТ наличия плана
            на текущий год, но не объявляет его отсутствие нарушением —
            обязанность вести производственный контроль зависит от того,
            эксплуатирует ли организация ОПО, и полноту сведений определяет
            специалист (прецедент интервала тренировок и требования ЭПБ).
          */}
          {!loading && !error ? (
            <p className="text-sm text-muted-foreground">
              {readiness.current_year_plan_exists
                ? "План производственного контроля на текущий год заведён."
                : "Плана производственного контроля на текущий год в системе нет."}{" "}
              Обязанность вести производственный контроль зависит от того,
              эксплуатирует ли организация опасные производственные объекты, —
              применимость определяет специалист.
            </p>
          ) : null}
          {!loading && !error && measureRegistry.total === 0 ? (
            <EmptyState
              title="Мероприятия производственного контроля не заведены"
              description="Заведите план на год и его мероприятия по разделам: обследования, экспертиза и диагностирование, обучение и аттестация, готовность к авариям, устранение нарушений, отчётность."
            />
          ) : null}
          {!loading && !error && measureRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "title", header: "Мероприятие" },
                {
                  accessorKey: "section_label",
                  header: "Раздел плана",
                  cell: ({ row }) => row.original.section_label,
                },
                {
                  accessorKey: "due_on",
                  header: "Срок",
                  cell: ({ row }) => formatDate(row.original.due_on),
                },
                {
                  accessorKey: "responsible",
                  header: "Ответственный",
                  cell: ({ row }) => row.original.responsible || "—",
                },
                {
                  accessorKey: "status_label",
                  header: "Состояние",
                  cell: ({ row }) => row.original.status_label,
                },
                {
                  accessorKey: "completed_on",
                  header: "Выполнено",
                  cell: ({ row }) =>
                    row.original.completed_on
                      ? formatDate(row.original.completed_on)
                      : "—",
                },
              ]}
              data={measureRegistry.pagedItems}
              pageIndex={measureRegistry.pageIndex}
              pageSize={measureRegistry.pageSize}
              total={measureRegistry.total}
              onPageChange={measureRegistry.onPageChange}
              onPageSizeChange={measureRegistry.onPageSizeChange}
              onSearchChange={measureRegistry.onSearchChange}
              searchPlaceholder="Поиск по мероприятию, разделу, ответственному"
              caption="Мероприятия производственного контроля"
            />
          ) : null}
        </>
      ) : null}
      {section === "attestations" ? (
        <>
          {!loading && !error && attestationRegistry.total === 0 ? (
            <EmptyState
              title="Аттестации по промышленной безопасности не заведены"
              description="Внесите аттестации работников с областью из справочника (А.1, Б.1–Б.12): без области запись относится к другой дисциплине и в этот реестр не попадает."
            />
          ) : null}
          {!loading && !error && attestationRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "person_name", header: "Работник" },
                {
                  // Область словами: код «Б.9» человеку ничего не говорит.
                  accessorKey: "area_label",
                  header: "Область аттестации",
                  cell: ({ row }) => row.original.area_label,
                },
                {
                  accessorKey: "issued_at",
                  header: "Аттестован",
                  cell: ({ row }) =>
                    row.original.issued_at
                      ? formatDate(row.original.issued_at)
                      : "—",
                },
                {
                  accessorKey: "expires_at",
                  header: "Действует до",
                  cell: ({ row }) =>
                    row.original.expires_at
                      ? formatDate(row.original.expires_at)
                      : "не указан",
                },
                {
                  accessorKey: "validity_status_label",
                  header: "Состояние",
                  cell: ({ row }) => row.original.validity_status_label,
                },
              ]}
              data={attestationRegistry.pagedItems}
              pageIndex={attestationRegistry.pageIndex}
              pageSize={attestationRegistry.pageSize}
              total={attestationRegistry.total}
              onPageChange={attestationRegistry.onPageChange}
              onPageSizeChange={attestationRegistry.onPageSizeChange}
              onSearchChange={attestationRegistry.onSearchChange}
              searchPlaceholder="Поиск по работнику и области аттестации"
              caption="Аттестация по промышленной безопасности"
            />
          ) : null}
        </>
      ) : null}
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
          {/*
            Срез-105: устройства (срез-13) и работы по ним заводились только
            через API. Устройство заводится на объекте, поэтому кнопка есть
            только когда объект есть; работа — когда есть что обслуживать.
          */}
          {!loading && !error ? (
            <div className="flex flex-wrap gap-2">
              {data.facilities.length > 0 ? (
                <OpoDeviceFormDialog
                  facilities={data.facilities}
                  onSubmitted={() => void reload()}
                  trigger={<Button>Завести устройство</Button>}
                />
              ) : (
                <p className="text-sm text-muted-foreground">
                  Устройства учитываются на объекте: сначала заведите объект в
                  секции «Объекты (ОПО)».
                </p>
              )}
              {data.devices.length > 0 ? (
                <OpoDeviceWorkFormDialog
                  devices={data.devices}
                  onSubmitted={() => void reload()}
                  trigger={<Button>Записать работу</Button>}
                />
              ) : null}
            </div>
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
                  // Срез-105: срок заключения и состояние ЭПБ — одна колонка:
                  // восьмая вывела бы таблицу за UX-бюджет (7), а действия
                  // строке нужнее. «Заключения нет» остаётся отдельным
                  // состоянием, а не пустой датой.
                  accessorKey: "epb_status_label",
                  header: "Экспертиза",
                  cell: ({ row }) => (
                    <span>
                      {row.original.epb_status_label}
                      {row.original.epb_valid_until ? (
                        <span className="ml-1 text-muted-foreground">
                          до {formatDate(row.original.epb_valid_until)}
                        </span>
                      ) : null}
                    </span>
                  ),
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
                {
                  id: "actions",
                  header: "Действия",
                  cell: ({ row }) => (
                    <div className="flex gap-1">
                      <OpoDeviceFormDialog
                        facilities={data.facilities}
                        initialData={row.original}
                        onSubmitted={() => void reload()}
                        trigger={
                          <Button variant="ghost" size="sm">
                            Изменить
                          </Button>
                        }
                      />
                      <OpoDeviceWorkFormDialog
                        devices={data.devices}
                        presetDeviceId={row.original.id}
                        onSubmitted={() => void reload()}
                        trigger={
                          <Button variant="ghost" size="sm">
                            Работа
                          </Button>
                        }
                      />
                    </div>
                  ),
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
      {/*
        Срез-105: ручки объектов (срез-12) работали только через API — реестр
        звал «внесите объекты из свидетельства», а внести их было негде.
      */}
      {section === "facilities" && !loading && !error ? (
        <div>
          <OpoFacilityFormDialog
            sites={data.sites}
            onSubmitted={() => void reload()}
            trigger={<Button>Завести объект</Button>}
          />
        </div>
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
            {
              id: "actions",
              header: "Действия",
              cell: ({ row }) => (
                <OpoFacilityFormDialog
                  sites={data.sites}
                  initialData={row.original}
                  onSubmitted={() => void reload()}
                  trigger={
                    <Button variant="ghost" size="sm">
                      Изменить
                    </Button>
                  }
                />
              ),
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
