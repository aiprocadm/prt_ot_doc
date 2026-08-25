import { useCallback } from "react";

import { ecologyApi } from "@/api/ecology";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
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
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        facilities: await ecologyApi.listFacilities(),
        readiness: await ecologyApi.readiness(),
      }),
      [],
    ),
    initialData: {
      facilities: [],
      readiness: {
        total_facilities: 0,
        by_category: { I: 0, II: 0, III: 0, IV: 0 },
        excluded_facilities: 0,
        never_actualized: 0,
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
        ]}
      />

      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка объектов НВОС" /> : null}
      {/*
        ГРАНИЦА, названная НА ЭКРАНЕ (прецедент интервала тренировок и
        требования ЭПБ): категорию объекта присваивают при постановке на
        государственный учёт по критериям постановления Правительства —
        мощность, виды воздействия, применяемые технологии. Этих данных в
        системе нет, поэтому платформа хранит внесённое, а не вычисляет.
      */}
      {!loading && !error ? (
        <p className="text-sm text-muted-foreground">
          Категория объекта присваивается при постановке на государственный учёт
          и хранится здесь как внесённая: платформа её не вычисляет — критерии
          опираются на мощность, виды воздействия и применяемые технологии,
          которых в системе нет.
        </p>
      ) : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Объекты НВОС не заведены"
          description="Внесите объекты из свидетельства о постановке на государственный учёт: наименование, код объекта в реестре и категорию."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
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
    </div>
  );
};

export default EcologyPage;
