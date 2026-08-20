import { useCallback } from "react";
import { Link } from "react-router-dom";

import { sitesApi, type Site } from "@/api/sites";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Badge } from "@/components/ui/badge";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";

/**
 * Реестр площадок (BIZ-54-57 срез-3, Доп. №1 разд. 57.1).
 *
 * Экрана площадок в интерфейсе не было вовсе: площадки жили только выпадающими
 * списками внутри мастеров. Карточка 360° без него была бы страницей, до
 * которой нельзя дойти — «работает» и «доступно» это разные вещи.
 *
 * Экран ЯДРА, а не дисциплины: он ведёт к карточке по всем дисциплинам сразу,
 * и выключение модуля «Пожарная безопасность» не должно его прятать.
 */

const SitesPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => sitesApi.list(), []),
    initialData: { items: [] as Site[], total: 0 },
    errorMessage: "Не удалось загрузить площадки",
  });

  const registry = useLocalRegistry({
    items: data.items,
    match: (item, query) =>
      [item.name, item.address, item.hazard_class, item.opo_register_number]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Площадки"
        description="Объекты предприятия. Из карточки площадки виден статус по всем дисциплинам сразу."
        stats={[
          { label: "Площадок", value: data.total },
          {
            label: "Из них ОПО",
            value: data.items.filter(
              (site) => site.is_hazardous_production_facility,
            ).length,
          },
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка площадок" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Площадок нет"
          description="Площадки заводятся в справочниках предприятия."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            {
              accessorKey: "name",
              header: "Площадка",
              cell: ({ row }) => (
                <Link
                  to={`/sites/${row.original.id}`}
                  className="underline underline-offset-4"
                >
                  {row.original.name}
                </Link>
              ),
            },
            {
              accessorKey: "address",
              header: "Адрес",
              cell: ({ row }) => row.original.address || "—",
            },
            {
              accessorKey: "hazard_class",
              header: "Класс опасности",
              cell: ({ row }) => row.original.hazard_class || "—",
            },
            {
              accessorKey: "opo_register_number",
              header: "ОПО",
              cell: ({ row }) =>
                row.original.is_hazardous_production_facility ? (
                  <Badge variant="secondary">
                    {row.original.opo_register_number || "без номера"}
                  </Badge>
                ) : (
                  "—"
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
          searchPlaceholder="Поиск по названию, адресу, номеру ОПО"
          caption="Реестр площадок"
        />
      ) : null}
    </div>
  );
};

export default SitesPage;
