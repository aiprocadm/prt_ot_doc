import { useCallback, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import {
  INTERNSHIP_STATUS_TITLES,
  internshipsApi,
  type InternshipDto,
  type InternshipSummaryDto,
} from "@/api/internships";
import { fetchAllPersons } from "@/api/personsApi";
import { Can } from "@/components/permissions/Can";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { InternshipFormDialog } from "@/features/internships/InternshipFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { PERMISSIONS } from "@/permissions/permissions";
import type { PersonDto } from "@/types/dto/persons";

type InternshipsData = {
  items: InternshipDto[];
  persons: PersonDto[];
  summary: InternshipSummaryDto;
};

const EMPTY_SUMMARY: InternshipSummaryDto = {
  total: 0,
  by_status: {},
  completed_short: 0,
  active_without_mentor: 0,
};

const statusVariant = (
  status: string,
): "default" | "secondary" | "destructive" | "outline" => {
  if (status === "in_progress") return "default";
  if (status === "cancelled") return "outline";
  return "secondary";
};

/**
 * Общий экран стажировок — один на все дисциплины (срез-7 завёл сущность,
 * срез-41 — экран). Контур БДД показывает только свои счётчики; здесь реестр
 * целиком, и плитки шапки считает СЕРВЕР (``/internships/summary``), а не
 * загруженная страница списка.
 *
 * ГРАНИЦА: «Недобор смен» и «без наставника» — факты о записях. Нужна ли
 * стажировка и допущен ли человек к самостоятельной работе, экран не решает.
 */
const InternshipsPage = () => {
  const [statusFilter, setStatusFilter] = useState("");

  const loader = useCallback(async (): Promise<InternshipsData> => {
    const [items, persons, summary] = await Promise.all([
      internshipsApi.list(statusFilter ? { status: statusFilter } : {}),
      fetchAllPersons(),
      internshipsApi.summary(),
    ]);
    return { items, persons, summary };
  }, [statusFilter]);

  const { data, loading, error, reload } = useAsyncResource<InternshipsData>({
    loader,
    initialData: { items: [], persons: [], summary: EMPTY_SUMMARY },
    errorMessage: "Не удалось загрузить стажировки",
  });

  const registry = useLocalRegistry({
    items: data.items,
    match: (item, query) =>
      [
        item.person_name,
        item.mentor_name ?? "",
        item.subject ?? "",
        item.status_label,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const onChanged = useCallback(() => void reload(), [reload]);

  const columns: ColumnDef<InternshipDto, unknown>[] = [
    {
      id: "person",
      header: "Стажёр",
      cell: ({ row }) => (
        <span className="font-medium">{row.original.person_name}</span>
      ),
    },
    {
      id: "mentor",
      header: "Наставник",
      cell: ({ row }) =>
        row.original.mentor_name ?? (
          <span className="text-muted-foreground">не назначен</span>
        ),
    },
    {
      accessorKey: "subject",
      header: "На что",
      cell: ({ row }) => row.original.subject || "—",
    },
    {
      id: "discipline",
      header: "Дисциплина",
      cell: ({ row }) =>
        row.original.discipline_label ?? (
          <span className="text-muted-foreground">не размечена</span>
        ),
    },
    {
      id: "shifts",
      header: "Смен",
      cell: ({ row }) => {
        const item = row.original;
        return (
          <span className="inline-flex items-center gap-2">
            <span>
              {item.completed_shifts} из {item.planned_shifts}
            </span>
            {item.completed_short ? (
              <Badge variant="destructive">Недобор смен</Badge>
            ) : null}
          </span>
        );
      },
    },
    {
      accessorKey: "status",
      header: "Состояние",
      cell: ({ row }) => (
        <Badge variant={statusVariant(row.original.status)}>
          {row.original.status_label}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: "Действия",
      cell: ({ row }) => (
        <Can
          permission={PERMISSIONS.TRAINING_ASSIGN}
          fallback={<span className="text-muted-foreground">—</span>}
        >
          <InternshipFormDialog
            persons={data.persons}
            initialData={row.original}
            onSubmitted={onChanged}
            trigger={
              <Button variant="ghost" size="sm">
                Изменить
              </Button>
            }
          />
        </Can>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Стажировки"
        description="Кто у кого стажируется и сколько смен пройдено. Один реестр на все дисциплины: контур БДД и другие показывают из него только своё."
        stats={[
          { label: "Всего", value: data.summary.total },
          {
            label: "Идёт",
            value: data.summary.by_status.in_progress ?? 0,
            hint: `назначено: ${data.summary.by_status.planned ?? 0}`,
          },
          {
            label: "Завершены с недобором",
            value: data.summary.completed_short,
            hint: "смен меньше плана — факт, не вердикт",
          },
          {
            label: "Без наставника",
            value: data.summary.active_without_mentor,
            hint: "назначены или идут; некому подтвердить смены",
          },
        ]}
        actions={
          <Can
            permission={PERMISSIONS.TRAINING_ASSIGN}
            fallback={<Button disabled>Назначить стажировку</Button>}
          >
            <InternshipFormDialog
              persons={data.persons}
              onSubmitted={onChanged}
              trigger={<Button>Назначить стажировку</Button>}
            />
          </Can>
        }
      />
      <Card>
        <CardContent className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-3">
            <select
              className="h-9 rounded-md border px-3 text-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label="Фильтр по состоянию"
            >
              <option value="">Все состояния</option>
              {Object.entries(INTERNSHIP_STATUS_TITLES).map(([code, title]) => (
                <option key={code} value={code}>
                  {title}
                </option>
              ))}
            </select>
          </div>

          <ErrorState
            error={error ?? undefined}
            onRetry={() => void reload()}
          />
          {loading ? <LoadingScreen label="Загрузка стажировок" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState
              title="Стажировок нет"
              description={
                registry.query || statusFilter
                  ? "Измените запрос или фильтр."
                  : "Назначьте первую: кому, у кого и сколько смен по плану."
              }
            />
          ) : null}
          {!loading && !error && registry.total > 0 ? (
            <RegistryTable
              columns={columns}
              data={registry.pagedItems}
              pageIndex={registry.pageIndex}
              pageSize={registry.pageSize}
              total={registry.total}
              onPageChange={registry.onPageChange}
              onPageSizeChange={registry.onPageSizeChange}
              onSearchChange={registry.onSearchChange}
              searchPlaceholder="Поиск по ФИО, наставнику или предмету"
              caption="Реестр стажировок по всем дисциплинам"
            />
          ) : null}
          <p className="text-xs text-muted-foreground">
            «Недобор смен» — смен пройдено меньше, чем по плану, а стажировка
            уже завершена. Это факт о записи. Нужна ли стажировка и допущен ли
            человек к самостоятельной работе — решает приказ, а не программа.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default InternshipsPage;
