import { useCallback, useMemo, useState } from "react";
import { Can } from "@/components/permissions/Can";
import { PERMISSIONS } from "@/permissions/permissions";

import {
  FIRE_EQUIPMENT_STATUS_TITLES,
  FIRE_EQUIPMENT_TITLES,
  FIRE_MAINTENANCE_RESULT_TITLES,
  fireSafetyApi,
  type FireEquipmentKind,
} from "@/api/fireSafety";
import { operationsApi } from "@/api/operations";
import { sitesApi } from "@/api/sites";
import { EmptyState } from "@/components/common/EmptyState";
import { deniedNotice } from "@/api/partial";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { disciplineIncidentsStat } from "@/components/common/disciplineIncidentsStat";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { FireDocumentFormDialog } from "@/features/fire-safety/FireDocumentFormDialog";
import { FireEquipmentFormDialog } from "@/features/fire-safety/FireEquipmentFormDialog";
import { FireMaintenanceFormDialog } from "@/features/fire-safety/FireMaintenanceFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

/** Подпись срока: просроченный называется просроченным, а не «датой в прошлом». */
const dueLabel = (value?: string | null): string => {
  if (!value) return "—";
  const due = new Date(value);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const shown = formatDate(value);
  return due < today ? `${shown} · просрочен` : shown;
};

const FireSafetyPage = () => {
  // Разд. 59.1: три задачи — «объекты защиты», «средства и системы» и
  // «документы» — показываются ПО ОДНОЙ (прецедент склада), иначе экран
  // растёт таблицами.
  const [section, setSection] = useState<"sites" | "equipment" | "documents">(
    "sites",
  );

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getFireSafetySnapshot(), []),
    initialData: { denied: [], sites: [], inspections: [], tasks: [] },
    errorMessage: "Не удалось загрузить объекты ПБ",
  });

  const fire = useAsyncResource({
    loader: useCallback(
      async () => ({
        equipment: await fireSafetyApi.listEquipment(),
        documents: await fireSafetyApi.listDocuments(),
        readiness: await fireSafetyApi.readiness(),
        // Площадки — ядровой справочник: средство и документ привязывают к
        // площадке выбором, а не вводом id (срез-103).
        sites: (await sitesApi.list()).items,
      }),
      [],
    ),
    initialData: {
      equipment: [],
      documents: [],
      sites: [],
      readiness: {
        incidents_open: 0,
        total_units: 0,
        overdue_recharge: 0,
        overdue_inspection: 0,
        due_soon: 0,
        due_soon_days: 30,
        overdue_fire_briefings: 0,
        fire_documents: 0,
        overdue_documents: 0,
        units_without_maintenance: 0,
        // Тренировки живут на своём экране (/fire-training); здесь они только
        // часть той же сводки готовности, поэтому в заглушке нули.
        overdue_drills: 0,
        planned_drills: 0,
        last_drill_on: null,
        days_since_last_drill: null,
      },
    },
    errorMessage: "Не удалось загрузить средства пожаротушения",
  });

  const items = useMemo(
    () =>
      data.sites.map((site) => ({
        ...site,
        inspections: data.inspections.filter((item) => item.site_id === site.id)
          .length,
      })),
    [data],
  );
  const registry = useLocalRegistry({
    items,
    match: (item, query) =>
      [item.name, item.address, item.hazard_class, item.contact_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const equipmentRegistry = useLocalRegistry({
    items: fire.data.equipment,
    match: (item, query) =>
      [
        item.label,
        item.location,
        FIRE_EQUIPMENT_TITLES[item.kind as FireEquipmentKind] ?? item.kind,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const documentRegistry = useLocalRegistry({
    items: fire.data.documents,
    match: (item, query) =>
      [
        item.title,
        item.kind_label,
        item.number,
        item.location,
        item.responsible,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const { readiness } = fire.data;
  const overdueTotal =
    readiness.overdue_recharge + readiness.overdue_inspection;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Пожарная безопасность"
        description="Площадки тенанта с их классом опасности и связанными проверками, а также первичные средства пожаротушения и системы защиты с регламентными сроками."
        stats={[
          { label: "Площадок", value: data.sites.length },
          { label: "Проверок", value: data.inspections.length },
          {
            label: "Открытых задач",
            value: data.tasks.filter((task) => task.status !== "done").length,
          },
          // Разд. 54.1 «готовность к проверке МЧС»: просрочка — первое, что
          // спрашивает инспектор, поэтому она в шапке, а не внутри таблицы.
          { label: "Просрочено сроков", value: overdueTotal },
          {
            label: `Истекает за ${readiness.due_soon_days} дн.`,
            value: readiness.due_soon,
          },
          // Разд. 54.1 «контроль сроков»: просроченный противопожарный
          // инструктаж — такое же нарушение, как непроверенный огнетушитель.
          {
            label: "Просроченных инструктажей ПБ",
            value: readiness.overdue_fire_briefings,
          },
          // Разд. 54.1 «регламентные работы»: срок без единой записи о работе —
          // обещание, а не доказательство; инспектор просит показать предыдущее
          // ТО, а не назвать дату следующего.
          {
            label: "Без подтверждения ТО",
            value: readiness.units_without_maintenance,
          },
          // Разд. 54.1 «Документы ПБ»: просроченный пересмотр инструкции —
          // такое же нарушение, как непроверенный огнетушитель. Сколько
          // документов ОБЯЗАТЕЛЬНО, платформа не судит — см. подпись секции.
          {
            label: "Просрочен пересмотр документов",
            value: readiness.overdue_documents,
          },
          // Доп. №1 разд. 57.4: происшествия контура — той же формулой, что
          // разрез у директора; ссылка ведёт в общий реестр (срез-49).
          disciplineIncidentsStat("fire_safety", readiness.incidents_open),
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["sites", "Объекты защиты"],
            ["equipment", "Средства и системы"],
            ["documents", "Документы ПБ"],
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

      {section === "sites" ? (
        <>
          <ErrorState
            error={error ?? undefined}
            onRetry={() => void reload()}
          />
          {deniedNotice(data.denied) ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-600/50 dark:bg-amber-950/30 dark:text-amber-50">
              {deniedNotice(data.denied)}
            </p>
          ) : null}
          {loading ? <LoadingScreen label="Загрузка объектов защиты" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState
              title="Площадки не найдены"
              description="Добавьте записи площадок в тенант."
            />
          ) : null}
          {!loading && !error && registry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "name", header: "Объект" },
                {
                  accessorKey: "hazard_class",
                  header: "Категория",
                  cell: ({ row }) => row.original.hazard_class || "—",
                },
                {
                  accessorKey: "inspections",
                  header: "Проверки",
                  cell: ({ row }) => `${row.original.inspections} шт.`,
                },
                {
                  accessorKey: "contact_name",
                  header: "Ответственный",
                  cell: ({ row }) => row.original.contact_name || "—",
                },
                {
                  accessorKey: "address",
                  header: "Адрес",
                  cell: ({ row }) => row.original.address || "—",
                },
              ]}
              data={registry.pagedItems}
              pageIndex={registry.pageIndex}
              pageSize={registry.pageSize}
              total={registry.total}
              onPageChange={registry.onPageChange}
              onPageSizeChange={registry.onPageSizeChange}
              onSearchChange={registry.onSearchChange}
              searchPlaceholder="Поиск по площадке, адресу, категории"
              caption="Реестр объектов защиты"
            />
          ) : null}
        </>
      ) : section === "documents" ? (
        <>
          <ErrorState
            error={fire.error ?? undefined}
            onRetry={() => void fire.reload()}
          />
          {fire.loading ? (
            <LoadingScreen label="Загрузка документов ПБ" />
          ) : null}
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ (прецедент интервала тренировок):
            платформа НЕ объявляет, какие документы объекту обязательны —
            декларация нужна не всем объектам, план эвакуации не всем этажам,
            а признаков применимости в данных нет. Показываем, что заведено и
            что просрочено по пересмотру; перечень обязательного — за
            специалистом.
          */}
          {!fire.loading && !fire.error ? (
            <p className="text-sm text-muted-foreground">
              Реестр показывает документы, которые вы завели, и их срок
              пересмотра. Какие из них обязательны именно для вашего объекта,
              определяет специалист: применимость декларации ПБ и планов
              эвакуации зависит от характеристик объекта, которых в данных нет.
            </p>
          ) : null}
          {/*
            Срез-103: ручки документов (срез-11) работали только через API —
            реестр звал «внесите приказы, инструкции, планы эвакуации», а
            внести их было негде. Одна главная кнопка на секцию.
          */}
          {!fire.loading && !fire.error ? (
            <div>
              <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                <FireDocumentFormDialog
                  sites={fire.data.sites}
                  onSubmitted={() => void fire.reload()}
                  trigger={<Button>Завести документ</Button>}
                />
              </Can>
            </div>
          ) : null}
          {!fire.loading && !fire.error && documentRegistry.total === 0 ? (
            <EmptyState
              title="Документы ПБ не заведены"
              description="Внесите приказы, инструкции о мерах ПБ, планы эвакуации, регламенты, декларацию и журналы — срок пересмотра попадёт в готовность к проверке."
            />
          ) : null}
          {!fire.loading && !fire.error && documentRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "title", header: "Документ" },
                {
                  accessorKey: "kind_label",
                  header: "Вид",
                  cell: ({ row }) => row.original.kind_label,
                },
                {
                  accessorKey: "number",
                  header: "Номер",
                  cell: ({ row }) => row.original.number || "—",
                },
                {
                  accessorKey: "location",
                  header: "Помещение",
                  cell: ({ row }) => row.original.location || "—",
                },
                {
                  accessorKey: "review_due",
                  header: "Пересмотр",
                  cell: ({ row }) =>
                    row.original.review_due
                      ? formatDate(row.original.review_due)
                      : "бессрочный",
                },
                {
                  accessorKey: "status_label",
                  header: "Состояние",
                  cell: ({ row }) => row.original.status_label,
                },
                {
                  id: "actions",
                  header: "Действия",
                  cell: ({ row }) => (
                    <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                      <FireDocumentFormDialog
                        sites={fire.data.sites}
                        initialData={row.original}
                        onSubmitted={() => void fire.reload()}
                        trigger={
                          <Button variant="ghost" size="sm">
                            Изменить
                          </Button>
                        }
                      />
                    </Can>
                  ),
                },
              ]}
              data={documentRegistry.pagedItems}
              pageIndex={documentRegistry.pageIndex}
              pageSize={documentRegistry.pageSize}
              total={documentRegistry.total}
              onPageChange={documentRegistry.onPageChange}
              onPageSizeChange={documentRegistry.onPageSizeChange}
              onSearchChange={documentRegistry.onSearchChange}
              searchPlaceholder="Поиск по названию, виду, номеру, помещению"
              caption="Документы пожарной безопасности"
            />
          ) : null}
        </>
      ) : (
        <>
          <ErrorState
            error={fire.error ?? undefined}
            onRetry={() => void fire.reload()}
          />
          {fire.loading ? (
            <LoadingScreen label="Загрузка средств пожаротушения" />
          ) : null}
          {/*
            Срез-103: средства (срез-4) и работы по ним (срез-14) заводились
            только через API. Две кнопки секции: завести средство и записать
            работу; вторая появляется, когда есть что обслуживать.
          */}
          {!fire.loading && !fire.error ? (
            <div className="flex flex-wrap gap-2">
              <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                <FireEquipmentFormDialog
                  sites={fire.data.sites}
                  onSubmitted={() => void fire.reload()}
                  trigger={<Button>Завести средство</Button>}
                />
              </Can>
              {fire.data.equipment.length > 0 ? (
                <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                  <FireMaintenanceFormDialog
                    equipment={fire.data.equipment}
                    onSubmitted={() => void fire.reload()}
                    trigger={<Button>Записать работу</Button>}
                  />
                </Can>
              ) : null}
            </div>
          ) : null}
          {!fire.loading && !fire.error && equipmentRegistry.total === 0 ? (
            <EmptyState
              title="Средства пожаротушения не заведены"
              description="Внесите огнетушители, краны, щиты и системы защиты — сроки перезарядки и поверки попадут в готовность к проверке."
            />
          ) : null}
          {!fire.loading && !fire.error && equipmentRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "label", header: "Наименование" },
                {
                  // Срез-111: вид и состояние — одна колонка. Списанное
                  // средство должно быть видно сразу (оно не считается в
                  // готовности), а восьмая колонка вывела бы таблицу за
                  // UX-бюджет.
                  accessorKey: "kind",
                  header: "Вид и состояние",
                  cell: ({ row }) => (
                    <span>
                      {FIRE_EQUIPMENT_TITLES[
                        row.original.kind as FireEquipmentKind
                      ] ?? row.original.kind}
                      {row.original.status !== "active" ? (
                        <span className="ml-1 text-muted-foreground">
                          ·{" "}
                          {row.original.status_label ??
                            FIRE_EQUIPMENT_STATUS_TITLES[row.original.status] ??
                            row.original.status}
                        </span>
                      ) : null}
                    </span>
                  ),
                },
                {
                  accessorKey: "location",
                  header: "Место",
                  cell: ({ row }) => row.original.location || "—",
                },
                {
                  accessorKey: "recharge_due",
                  header: "Перезарядка",
                  cell: ({ row }) => dueLabel(row.original.recharge_due),
                },
                {
                  accessorKey: "inspection_due",
                  header: "Поверка / ТО",
                  cell: ({ row }) => dueLabel(row.original.inspection_due),
                },
                {
                  // Разд. 54.1: последняя ПОДТВЕРЖДЁННАЯ работа. Отсутствие
                  // записей названо словами — пустая ячейка читалась бы как
                  // «данные не подгрузились», а это другое.
                  accessorKey: "last_maintenance_on",
                  header: "Последнее ТО",
                  cell: ({ row }) =>
                    row.original.last_maintenance_on
                      ? `${formatDate(row.original.last_maintenance_on)} · ${
                          FIRE_MAINTENANCE_RESULT_TITLES[
                            row.original.last_maintenance_result ?? ""
                          ] ?? "—"
                        }`
                      : "нет записей",
                },
                {
                  id: "actions",
                  header: "Действия",
                  cell: ({ row }) => (
                    <div className="flex gap-1">
                      <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                        <FireEquipmentFormDialog
                          sites={fire.data.sites}
                          initialData={row.original}
                          onSubmitted={() => void fire.reload()}
                          trigger={
                            <Button variant="ghost" size="sm">
                              Изменить
                            </Button>
                          }
                        />
                      </Can>
                      <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                        <FireMaintenanceFormDialog
                          equipment={fire.data.equipment}
                          presetEquipmentId={row.original.id}
                          onSubmitted={() => void fire.reload()}
                          trigger={
                            <Button variant="ghost" size="sm">
                              Работа
                            </Button>
                          }
                        />
                      </Can>
                    </div>
                  ),
                },
              ]}
              data={equipmentRegistry.pagedItems}
              pageIndex={equipmentRegistry.pageIndex}
              pageSize={equipmentRegistry.pageSize}
              total={equipmentRegistry.total}
              onPageChange={equipmentRegistry.onPageChange}
              onPageSizeChange={equipmentRegistry.onPageSizeChange}
              onSearchChange={equipmentRegistry.onSearchChange}
              searchPlaceholder="Поиск по наименованию, месту, виду"
              caption="Средства пожаротушения и системы защиты"
            />
          ) : null}
        </>
      )}
    </div>
  );
};

export default FireSafetyPage;
