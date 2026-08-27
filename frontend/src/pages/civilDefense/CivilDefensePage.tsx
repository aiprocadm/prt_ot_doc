import { type ColumnDef } from "@tanstack/react-table";
import { useCallback, useState } from "react";

import {
  civilDefenseApi,
  type DrillDto,
  type FormationDto,
} from "@/api/civilDefense";
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

const DRILL_COLUMNS: ColumnDef<DrillDto, unknown>[] = [
  { accessorKey: "title", header: "Учение" },
  {
    accessorKey: "kind_label",
    header: "Вид",
    cell: ({ row }) => row.original.kind_label,
  },
  {
    accessorKey: "planned_on",
    header: "По плану",
    cell: ({ row }) => formatDate(row.original.planned_on),
  },
  {
    accessorKey: "held_on",
    header: "Проведено",
    cell: ({ row }) =>
      row.original.held_on
        ? formatDate(row.original.held_on)
        : "не проводилось",
  },
  {
    accessorKey: "status_label",
    header: "Состояние",
    cell: ({ row }) => row.original.status_label,
  },
  {
    accessorKey: "formation_name",
    header: "Формирование",
    cell: ({ row }) => row.original.formation_name || "весь персонал",
  },
  {
    accessorKey: "outcome_label",
    header: "Результат",
    cell: ({ row }) => row.original.outcome_label || "—",
  },
];

const CivilDefensePage = () => {
  // Секции ПО ОДНОЙ (прецедент экранов ПБ, ПромБеза и экологии): реестр
  // формирований и план-график учений — разные задачи специалиста.
  const [section, setSection] = useState<"formations" | "drills">("formations");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(
      async () => ({
        formations: await civilDefenseApi.listFormations(),
        drills: await civilDefenseApi.listDrills(),
        readiness: await civilDefenseApi.readiness(),
      }),
      [],
    ),
    initialData: {
      formations: [] as FormationDto[],
      drills: [] as DrillDto[],
      readiness: {
        total_formations: 0,
        by_kind: { nasf: 0, nfgo: 0 },
        without_commander: 0,
        members_active: 0,
        drills_total: 0,
        drills_overdue: 0,
        drills_held_this_year: 0,
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

  const drillRegistry = useLocalRegistry({
    items: data.drills,
    match: (item, query) =>
      [item.title, item.kind_label, item.status_label, item.formation_name]
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
          // Разд. 56.1 «учения»: просрочка — факт по внесённому плану, а не
          // вывод платформы о нарушении периодичности.
          { label: "Учения просрочены", value: readiness.drills_overdue },
          {
            label: "Проведено за год",
            value: readiness.drills_held_this_year,
          },
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["formations", "Формирования"],
            ["drills", "Учения и тренировки"],
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
      {loading ? <LoadingScreen label="Загрузка формирований" /> : null}
      {/*
        ГРАНИЦА, названная НА ЭКРАНЕ (прецедент категории НВОС и интервала
        тренировок ПБ): обязанность создавать формирования и их штат следуют
        из категории организации по ГО и решений органа управления ГОЧС —
        платформа хранит внесённое, а не решает за орган.
      */}
      {section === "formations" && !loading && !error ? (
        <p className="text-sm text-muted-foreground">
          Нужно ли организации формирование и каков его штат, определяют
          категория по гражданской обороне и орган управления ГОЧС: платформа
          ведёт реестр внесённого и не выносит вердиктов.
        </p>
      ) : null}
      {section === "formations" &&
      !loading &&
      !error &&
      registry.total === 0 ? (
        <EmptyState
          title="Формирования не заведены"
          description="Внесите нештатные формирования: НАСФ (аварийно-спасательные) и НФГО (по обеспечению мероприятий ГО), их назначение и командиров из числа сотрудников."
        />
      ) : null}
      {section === "formations" && !loading && !error && registry.total > 0 ? (
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
      {section === "drills" && !loading && !error ? (
        <>
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ: периодичность учений установлена
            постановлением Правительства и зависит от категории организации по
            ГО — платформа ведёт внесённый план-график и не назначает сроки.
          */}
          <p className="text-sm text-muted-foreground">
            Периодичность учений установлена постановлением и категорией
            организации по гражданской обороне: платформа ведёт внесённый
            план-график и журнал проведённых, но сроки не назначает.
            «Просрочено» — это план, срок которого прошёл, а протокола нет.
          </p>
          {drillRegistry.total === 0 ? (
            <EmptyState
              title="План-график учений не заведён"
              description="Внесите учения и тренировки: командно-штабные, тактико-специальные, комплексные и объектовые. У проведённого обязателен результат — без него анализировать нечего."
            />
          ) : (
            <RegistryTable
              columns={DRILL_COLUMNS}
              data={drillRegistry.pagedItems}
              pageIndex={drillRegistry.pageIndex}
              pageSize={drillRegistry.pageSize}
              total={drillRegistry.total}
              onPageChange={drillRegistry.onPageChange}
              onPageSizeChange={drillRegistry.onPageSizeChange}
              onSearchChange={drillRegistry.onSearchChange}
              searchPlaceholder="Поиск по названию, виду, состоянию"
              caption="План-график учений и журнал проведённых"
            />
          )}
        </>
      ) : null}
    </div>
  );
};

export default CivilDefensePage;
