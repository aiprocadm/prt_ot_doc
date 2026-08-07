import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";

import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContractorFormDialog } from "@/features/contractors/ContractorFormDialog";
import { ContractorExpiringTab } from "@/features/contractors/ContractorExpiringTab";
import { ContractorRequirementsTab } from "@/features/contractors/ContractorRequirementsTab";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ContractorRegistry } from "@/types/dto/contractors";

type RegistryData = {
  contractors: ContractorRegistry[];
  employeeCounts: Map<string, number>;
  incidentCounts: Map<string, number>;
  expiringTotal: number;
};

const ContractorsPage = () => {
  const loader = useCallback(async (): Promise<RegistryData> => {
    const [registry, employees, incidents, expiring] = await Promise.all([
      contractorsApi.listRegistry(),
      contractorsApi.listEmployees(),
      contractorsApi.listIncidents(),
      // Expiring-docs is behind the tenant `contractors` feature gate, unlike the
      // registry/employees/incidents endpoints. Degrade gracefully so a
      // feature-opt-out tenant still sees the (ungated) registry instead of a
      // page-wide error; the stat just reads 0.
      contractorsApi.listExpiringDocuments().catch((e) => {
        if (isFeatureDisabledError(e)) return { items: [], total: 0 };
        throw e;
      }),
    ]);
    const employeeCounts = new Map<string, number>();
    employees.items.forEach((e) =>
      employeeCounts.set(
        e.contractor_id,
        (employeeCounts.get(e.contractor_id) ?? 0) + 1,
      ),
    );
    const incidentCounts = new Map<string, number>();
    incidents.items.forEach((i) =>
      incidentCounts.set(
        i.contractor_id,
        (incidentCounts.get(i.contractor_id) ?? 0) + 1,
      ),
    );
    return {
      contractors: registry.items,
      employeeCounts,
      incidentCounts,
      expiringTotal: expiring.total,
    };
  }, []);

  const { data, loading, error, reload } = useAsyncResource<RegistryData>({
    loader,
    initialData: {
      contractors: [],
      employeeCounts: new Map(),
      incidentCounts: new Map(),
      expiringTotal: 0,
    },
    errorMessage: "Не удалось загрузить реестр подрядчиков",
  });

  const rows = useMemo(
    () =>
      data.contractors.map((c) => ({
        ...c,
        employeeCount: data.employeeCounts.get(c.id) ?? 0,
        incidentCount: data.incidentCounts.get(c.id) ?? 0,
      })),
    [data],
  );

  const registry = useLocalRegistry({
    items: rows,
    match: (item, query) =>
      [item.name, item.status, item.inn, item.contact_person]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const columns: ColumnDef<(typeof rows)[number], unknown>[] = [
    {
      accessorKey: "name",
      header: "Контрагент",
      cell: ({ row }) => (
        <Link
          to={`/contractors/${row.original.id}`}
          className="font-medium text-primary hover:underline"
        >
          {row.original.name}
        </Link>
      ),
    },
    {
      accessorKey: "status",
      header: "Статус",
      cell: ({ row }) => row.original.status || "—",
    },
    {
      accessorKey: "inn",
      header: "ИНН",
      cell: ({ row }) => row.original.inn || "—",
    },
    {
      accessorKey: "employeeCount",
      header: "Сотрудники",
      cell: ({ row }) => `${row.original.employeeCount} чел.`,
    },
    {
      accessorKey: "incidentCount",
      header: "Инциденты",
      cell: ({ row }) => `${row.original.incidentCount} шт.`,
    },
    {
      accessorKey: "contact_person",
      header: "Контакт",
      cell: ({ row }) =>
        row.original.contact_person || row.original.contact_phone || "—",
    },
  ];

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Контрагенты и подрядчики"
        description="Реестр подрядчиков поверх backend `/contractors/*`: сотрудники, документы, допуски, инциденты."
        actions={
          <Can
            permission={PERMISSIONS.CONTRACTOR_MANAGE}
            fallback={<Button disabled>Новый контрагент</Button>}
          >
            <ContractorFormDialog
              trigger={<Button>Новый контрагент</Button>}
              onSubmitted={() => void reload()}
            />
          </Can>
        }
        stats={[
          { label: "Контрагентов", value: data.contractors.length },
          {
            label: "Сотрудников",
            value: [...data.employeeCounts.values()].reduce((a, b) => a + b, 0),
          },
          {
            label: "Инцидентов",
            value: [...data.incidentCounts.values()].reduce((a, b) => a + b, 0),
          },
          { label: "Истекающих документов", value: data.expiringTotal },
        ]}
      />

      <Tabs defaultValue="registry">
        <TabsList>
          <TabsTrigger value="registry">Реестр</TabsTrigger>
          <TabsTrigger value="expiring">Истекающие документы</TabsTrigger>
          <TabsTrigger value="requirements">
            Требования к документам
          </TabsTrigger>
        </TabsList>

        <TabsContent value="registry" className="space-y-3">
          <ErrorState
            error={error ?? undefined}
            onRetry={() => void reload()}
          />
          {loading ? <LoadingScreen label="Загрузка подрядчиков" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState
              title="Подрядчики не найдены"
              description="Добавьте контрагента или измените поиск."
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
              searchPlaceholder="Поиск по названию, ИНН, контакту"
              caption="Реестр подрядчиков"
            />
          ) : null}
        </TabsContent>

        <TabsContent value="expiring">
          <ContractorExpiringTab />
        </TabsContent>

        <TabsContent value="requirements">
          <ContractorRequirementsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ContractorsPage;
