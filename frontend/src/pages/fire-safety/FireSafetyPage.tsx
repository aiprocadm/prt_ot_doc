import { useCallback, useMemo, useState } from "react";

import {
  FIRE_EQUIPMENT_TITLES,
  FIRE_MAINTENANCE_RESULT_TITLES,
  fireSafetyApi,
  type FireEquipmentKind,
} from "@/api/fireSafety";
import { operationsApi } from "@/api/operations";
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
    initialData: { sites: [], inspections: [], tasks: [] },
    errorMessage: "Не удалось загрузить объекты ПБ",
  });

  const fire = useAsyncResource({
    loader: useCallback(
      async () => ({
        equipment: await fireSafetyApi.listEquipment(),
        documents: await fireSafetyApi.listDocuments(),
        readiness: await fireSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      equipment: [],
      documents: [],
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
                  accessorKey: "kind",
                  header: "Вид",
                  cell: ({ row }) =>
                    FIRE_EQUIPMENT_TITLES[
                      row.original.kind as FireEquipmentKind
                    ] ?? row.original.kind,
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
