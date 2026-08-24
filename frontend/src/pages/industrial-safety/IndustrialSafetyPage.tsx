import { useCallback } from "react";

import { industrialSafetyApi } from "@/api/industrialSafety";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

/**
 * Реестр ОПО (Доп. №1 разд. 54.2, срез-1).
 *
 * До этого экрана «ОПО» существовало тремя полями площадки, причём класс
 * опасности был свободной строкой, в которую клали и класс ОПО («II»), и
 * категорию пожарной опасности («В2»). Считать по классам было нечего, а
 * несколько объектов на одной площадке полями площадки не выражаются вовсе.
 */
const IndustrialSafetyPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        facilities: await industrialSafetyApi.listFacilities(),
        readiness: await industrialSafetyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      facilities: [],
      readiness: {
        total_facilities: 0,
        by_class: { I: 0, II: 0, III: 0, IV: 0 },
        excluded_facilities: 0,
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

  const { readiness } = data;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Промышленная безопасность"
        description="Реестр опасных производственных объектов: регистрационные сведения и класс опасности. От класса зависит режим надзора, поэтому разрез по классам — в шапке."
        stats={[
          { label: "Действующих ОПО", value: readiness.total_facilities },
          // I и II класс — постоянный государственный надзор и обязательная
          // декларация промышленной безопасности, поэтому они названы отдельно.
          { label: "I класс", value: readiness.by_class.I ?? 0 },
          { label: "II класс", value: readiness.by_class.II ?? 0 },
          { label: "III класс", value: readiness.by_class.III ?? 0 },
          { label: "IV класс", value: readiness.by_class.IV ?? 0 },
          {
            label: "Исключено из реестра",
            value: readiness.excluded_facilities,
          },
        ]}
      />

      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка реестра ОПО" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Опасные производственные объекты не заведены"
          description="Внесите объекты из свидетельства о регистрации: наименование, регистрационный номер и класс опасности. На одной площадке объектов может быть несколько."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
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
