import { type ColumnDef } from "@tanstack/react-table";
import { useCallback } from "react";

import { civilDefenseApi, type FormationDto } from "@/api/civilDefense";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";

/**
 * ГО и ЧС: реестр нештатных формирований (Доп. №1 разд. 56.1, срез-1).
 *
 * До этого экрана по разд. 56 не было НИЧЕГО: ни сущностей, ни ручек, ни
 * страницы — дисциплина существовала словарной строкой, а весь контент
 * сводился к комплекту документов GOCHS_BASE.
 */
const FORMATION_COLUMNS: ColumnDef<FormationDto, unknown>[] = [
  { accessorKey: "name", header: "Наименование" },
  {
    accessorKey: "kind_label",
    header: "Вид",
    cell: ({ row }) => row.original.kind_label,
  },
  {
    accessorKey: "purpose",
    header: "Назначение",
    cell: ({ row }) => row.original.purpose || "—",
  },
  {
    accessorKey: "commander_name",
    header: "Командир",
    cell: ({ row }) => row.original.commander_name || "не назначен",
  },
  {
    accessorKey: "members_active",
    header: "В составе",
    cell: ({ row }) =>
      row.original.members_active > 0
        ? `${row.original.members_active}`
        : "состав не внесён",
  },
];

const CivilDefensePage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        formations: await civilDefenseApi.listFormations(),
        readiness: await civilDefenseApi.readiness(),
      }),
      [],
    ),
    initialData: {
      formations: [] as FormationDto[],
      readiness: {
        total_formations: 0,
        by_kind: { nasf: 0, nfgo: 0 },
        without_commander: 0,
        members_active: 0,
      },
    },
    errorMessage: "Не удалось загрузить формирования ГО и ЧС",
  });

  const registry = useLocalRegistry({
    items: data.formations,
    match: (item, query) =>
      [item.name, item.kind_label, item.purpose, item.commander_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const { readiness } = data;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="ГО и ЧС"
        description="Нештатные формирования гражданской обороны: НАСФ и НФГО, командиры и составы из сотрудников организации."
        stats={[
          { label: "Формирований", value: readiness.total_formations },
          { label: "НАСФ", value: readiness.by_kind.nasf ?? 0 },
          { label: "НФГО", value: readiness.by_kind.nfgo ?? 0 },
          // ФАКТ о внесённом, а не вердикт: штат формирования платформа
          // не знает.
          { label: "Без командира", value: readiness.without_commander },
          { label: "Людей в составах", value: readiness.members_active },
        ]}
      />

      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка формирований" /> : null}
      {/*
        ГРАНИЦА, названная НА ЭКРАНЕ (прецедент категории НВОС и интервала
        тренировок ПБ): обязанность создавать формирования и их штат следуют
        из категории организации по ГО и решений органа управления ГОЧС —
        платформа хранит внесённое, а не решает за орган.
      */}
      {!loading && !error ? (
        <p className="text-sm text-muted-foreground">
          Нужно ли организации формирование и каков его штат, определяют
          категория по гражданской обороне и орган управления ГОЧС: платформа
          ведёт реестр внесённого и не выносит вердиктов.
        </p>
      ) : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Формирования не заведены"
          description="Внесите нештатные формирования: НАСФ (аварийно-спасательные) и НФГО (по обеспечению мероприятий ГО), их назначение и командиров из числа сотрудников."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={FORMATION_COLUMNS}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по названию, виду, командиру"
          caption="Реестр нештатных формирований"
        />
      ) : null}
    </div>
  );
};

export default CivilDefensePage;
