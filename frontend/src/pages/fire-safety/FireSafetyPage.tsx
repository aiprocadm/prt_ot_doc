import { useCallback, useMemo } from "react";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";

const FireSafetyPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getFireSafetySnapshot(), []),
    initialData: { sites: [], inspections: [], tasks: [] },
    errorMessage: "Не удалось загрузить объекты ПБ",
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

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Пожарная безопасность · объекты защиты"
        description="Вместо статического списка отображаются реальные площадки тенанта с их классом опасности и связанными проверками."
        stats={[
          { label: "Площадок", value: data.sites.length },
          { label: "Проверок", value: data.inspections.length },
          {
            label: "Открытых задач",
            value: data.tasks.filter((task) => task.status !== "done").length,
          },
        ]}
      />
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
    </div>
  );
};

export default FireSafetyPage;
