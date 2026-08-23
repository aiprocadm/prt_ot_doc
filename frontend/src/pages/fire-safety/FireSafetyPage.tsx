import { useCallback, useMemo, useState } from "react";

import {
  FIRE_EQUIPMENT_TITLES,
  fireSafetyApi,
  type FireEquipmentKind,
} from "@/api/fireSafety";
import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
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
  // Разд. 59.1: две задачи — «объекты защиты» и «средства и системы» —
  // показываются ПО ОДНОЙ (прецедент склада), иначе экран растёт таблицами.
  const [section, setSection] = useState<"sites" | "equipment">("sites");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getFireSafetySnapshot(), []),
    initialData: { sites: [], inspections: [], tasks: [] },
    errorMessage: "Не удалось загрузить объекты ПБ",
  });

  const fire = useAsyncResource({
    loader: useCallback(
      async () => ({
        equipment: await fireSafetyApi.listEquipment(),
        readiness: await fireSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      equipment: [],
      readiness: {
        total_units: 0,
        overdue_recharge: 0,
        overdue_inspection: 0,
        due_soon: 0,
        due_soon_days: 30,
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
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["sites", "Объекты защиты"],
            ["equipment", "Средства и системы"],
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
          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
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
