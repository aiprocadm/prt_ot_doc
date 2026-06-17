import { useCallback, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { permitsApi } from "@/api/permits";
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
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { PERMISSIONS } from "@/permissions/permissions";
import type { PermitDto } from "@/types/dto/permits";
import type { PersonDto } from "@/types/dto/persons";
import { formatDate } from "@/utils/datetime";
import { PermitFormDialog } from "@/features/permits/PermitFormDialog";
import { PermitExtendDialog } from "@/features/permits/PermitExtendDialog";
import { RevokePermitDialog } from "@/features/permits/RevokePermitDialog";

type PermitsData = {
  permits: PermitDto[];
  persons: PersonDto[];
  counts: { total: number; active: number; expired: number };
};

const permitBadge = (p: PermitDto): { label: string; variant: "default" | "secondary" | "destructive" } => {
  if (p.status === "revoked") return { label: "Отозван", variant: "secondary" };
  if (p.is_expired || p.status === "expired") return { label: "Просрочен", variant: "destructive" };
  return { label: "Действует", variant: "default" };
};

const PermitsPage = () => {
  const [statusFilter, setStatusFilter] = useState("");
  const [expiredOnly, setExpiredOnly] = useState(false);

  const loader = useCallback(async (): Promise<PermitsData> => {
    const params: Record<string, string | boolean | number> = {};
    if (expiredOnly) params.expired_only = true;
    else if (statusFilter) params.status = statusFilter;
    const [page, persons, total, active, expired] = await Promise.all([
      permitsApi.listPermits(params),
      fetchAllPersons(),
      permitsApi.countPermits({}),
      permitsApi.countPermits({ status: "active" }),
      permitsApi.countPermits({ expired_only: true })
    ]);
    return { permits: page.items, persons, counts: { total, active, expired } };
  }, [statusFilter, expiredOnly]);

  const { data, loading, error, reload } = useAsyncResource<PermitsData>({
    loader,
    initialData: { permits: [], persons: [], counts: { total: 0, active: 0, expired: 0 } },
    errorMessage: "Не удалось загрузить допуски"
  });

  const personName = useMemo(() => {
    const map = new Map(data.persons.map((p) => [p.id, p.full_name]));
    return (id: string) => map.get(id) ?? id;
  }, [data.persons]);

  const registry = useLocalRegistry({
    items: data.permits,
    match: (permit, query) =>
      [personName(permit.person_id), permit.permit_type, permit.status]
        .join(" ")
        .toLowerCase()
        .includes(query)
  });

  const onChanged = () => void reload();

  const columns: ColumnDef<PermitDto, unknown>[] = [
    {
      id: "person",
      header: "Сотрудник",
      cell: ({ row }) => <span className="font-medium">{personName(row.original.person_id)}</span>
    },
    { accessorKey: "permit_type", header: "Тип допуска" },
    {
      accessorKey: "issued_at",
      header: "Выдан",
      cell: ({ row }) => formatDate(row.original.issued_at) || "—"
    },
    {
      accessorKey: "valid_until",
      header: "Действует до",
      cell: ({ row }) => formatDate(row.original.valid_until) || "—"
    },
    {
      accessorKey: "status",
      header: "Статус",
      cell: ({ row }) => {
        const badge = permitBadge(row.original);
        return <Badge variant={badge.variant}>{badge.label}</Badge>;
      }
    },
    {
      id: "actions",
      header: "Действия",
      cell: ({ row }) => {
        const permit = row.original;
        if (permit.status === "revoked") return <span className="text-muted-foreground">—</span>;
        return (
          <Can permission={PERMISSIONS.PERMIT_MANAGE} fallback={<span className="text-muted-foreground">—</span>}>
            <div className="flex gap-2">
              {permit.status === "active" ? (
                <PermitFormDialog
                  persons={data.persons}
                  initialData={permit}
                  onSubmitted={onChanged}
                  trigger={
                    <Button variant="ghost" size="sm">
                      Изменить
                    </Button>
                  }
                />
              ) : null}
              <PermitExtendDialog
                permit={permit}
                onSubmitted={onChanged}
                trigger={
                  <Button variant="ghost" size="sm">
                    Продлить
                  </Button>
                }
              />
              <RevokePermitDialog
                permit={permit}
                onSubmitted={onChanged}
                trigger={
                  <Button variant="ghost" size="sm">
                    Отозвать
                  </Button>
                }
              />
            </div>
          </Can>
        );
      }
    }
  ];

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Личные допуски"
        description="Кто к чему допущен и до какого срока. Реестр поверх backend `/permits`."
        stats={[
          { label: "Всего", value: data.counts.total },
          { label: "Действует", value: data.counts.active },
          { label: "Просрочено", value: data.counts.expired }
        ]}
        actions={
          <Can
            permission={PERMISSIONS.PERMIT_MANAGE}
            fallback={
              <Button disabled>Новый допуск</Button>
            }
          >
            <PermitFormDialog
              persons={data.persons}
              onSubmitted={onChanged}
              trigger={<Button>Новый допуск</Button>}
            />
          </Can>
        }
      />
      <Card>
        <CardContent className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-3">
            <select
              className="h-9 rounded-md border px-3 text-sm disabled:opacity-60"
              value={statusFilter}
              disabled={expiredOnly}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label="Фильтр по статусу"
            >
              <option value="">Все статусы</option>
              <option value="active">Действует</option>
              <option value="expired">Просроченные</option>
              <option value="revoked">Отозван</option>
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={expiredOnly}
                onChange={(e) => setExpiredOnly(e.target.checked)}
              />
              Только просроченные
            </label>
          </div>

          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка допусков" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState
              title="Допуски не найдены"
              description={registry.query ? "Измените запрос поиска." : "В этом tenant пока нет допусков."}
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
              searchPlaceholder="Поиск по ФИО или типу допуска"
              caption="Реестр личных допусков"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default PermitsPage;
