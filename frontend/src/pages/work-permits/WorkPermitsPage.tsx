import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { workPermitsApi } from "@/api/workPermits";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import {
  SAFETY_SYSTEM_LABELS,
  STATUS_LABELS,
  WORK_TYPE_LABELS,
  labelOf,
} from "@/lib/workPermitVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { WorkPermitDto } from "@/types/dto/workPermits";

const STATUS_FILTERS = [
  "",
  "draft",
  "issued",
  "suspended",
  "closed",
  "cancelled",
];

export default function WorkPermitsPage() {
  const [status, setStatus] = useState("");
  const [counts, setCounts] = useState({ draft: 0, issued: 0, closed: 0 });

  const loader = useCallback(
    () => workPermitsApi.list(status ? { status } : {}).then((p) => p.items),
    [status],
  );
  const { data, loading, error, reload } = useAsyncResource<WorkPermitDto[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить наряды",
  });

  useEffect(() => {
    Promise.all([
      workPermitsApi.count({ status: "draft" }),
      workPermitsApi.count({ status: "issued" }),
      workPermitsApi.count({ status: "closed" }),
    ])
      .then(([draft, issued, closed]) => setCounts({ draft, issued, closed }))
      .catch(() => undefined);
  }, [data]);

  const registry = useLocalRegistry({
    items: data,
    match: (wp: WorkPermitDto, q: string) =>
      [wp.number ?? "", labelOf(WORK_TYPE_LABELS, wp.work_type), wp.zone_text]
        .join(" ")
        .toLowerCase()
        .includes(q),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium">Наряды-допуски</h1>
          <p className="text-sm text-muted-foreground">
            Черновики: {counts.draft} · Выдан: {counts.issued} · Закрыто:{" "}
            {counts.closed}
          </p>
        </div>
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <WorkPermitFormDialog
            trigger={<Button>Новый наряд</Button>}
            onSubmitted={() => void reload()}
          />
        </Can>
      </div>

      <div className="flex gap-2">
        <select
          className="h-9 rounded-md border px-3 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="Фильтр по статусу"
        >
          {STATUS_FILTERS.map((s) => (
            <option key={s || "all"} value={s}>
              {s ? (STATUS_LABELS[s] ?? s) : "Все статусы"}
            </option>
          ))}
        </select>
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка нарядов-допусков" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState
          title="Нарядов нет"
          description="Создайте первый наряд-допуск."
        />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable<WorkPermitDto>
          columns={[
            {
              accessorKey: "number",
              header: "№",
              cell: ({ row }) => row.original.number ?? "—",
            },
            {
              id: "work_type",
              header: "Вид работ",
              cell: ({ row }) =>
                labelOf(WORK_TYPE_LABELS, row.original.work_type),
            },
            {
              accessorKey: "zone_text",
              header: "Зона",
              cell: ({ row }) => row.original.zone_text,
            },
            {
              id: "safety_systems",
              header: "Системы безопасности",
              cell: ({ row }) => {
                const systems = row.original.safety_systems;
                if (!systems || systems.length === 0) return "—";
                return systems
                  .map((c) => SAFETY_SYSTEM_LABELS[c] ?? c)
                  .join(", ");
              },
            },
            {
              id: "members_count",
              header: "Бригада",
              cell: ({ row }) => String(row.original.members.length),
            },
            {
              id: "status",
              header: "Статус",
              cell: ({ row }) => <StatusBadge status={row.original.status} />,
            },
            {
              id: "open",
              header: "",
              cell: ({ row }) => (
                <Link
                  className="text-sm underline"
                  to={`/work-permits/${row.original.id}`}
                >
                  Открыть
                </Link>
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
          searchPlaceholder="Поиск по №, виду, зоне"
          caption="Наряды-допуски"
        />
      ) : null}
    </div>
  );
}
