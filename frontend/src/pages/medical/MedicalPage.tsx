import { useCallback, useMemo } from "react";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const MedicalPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getMedicalSnapshot(), []),
    initialData: { exams: [], persons: [], tasks: [] },
    errorMessage: "Не удалось загрузить медосмотры"
  });

  const items = useMemo(() => data.exams.map((exam) => ({ ...exam, person: data.persons.find((person) => person.id === exam.person_id) })), [data]);
  const registry = useLocalRegistry({ items, match: (item, query) => [item.person?.full_name, item.exam_type, item.conclusion].filter(Boolean).join(" ").toLowerCase().includes(query) });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Медосмотры и допуски"
        description="Реестр теперь использует реальный backend endpoint `/medical/exams` и связывает его с людьми и обязательствами."
        stats={[
          { label: "Медосмотров", value: data.exams.length },
          { label: "Просрочено", value: data.exams.filter((item) => new Date(item.valid_until) < new Date()).length },
          { label: "Задач по медосмотрам", value: data.tasks.length }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка медосмотров" /> : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Медосмотры не найдены" description="Добавьте записи медосмотров или создайте требования." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { id: "person", header: "Сотрудник", cell: ({ row }) => row.original.person?.full_name || row.original.person_id },
            { accessorKey: "exam_type", header: "Тип" },
            { accessorKey: "exam_date", header: "Дата", cell: ({ row }) => formatDate(row.original.exam_date) },
            { accessorKey: "valid_until", header: "Действует до", cell: ({ row }) => formatDate(row.original.valid_until) },
            {
              id: "state",
              header: "Состояние",
              cell: ({ row }) => <StatusBadge status={new Date(row.original.valid_until) < new Date() ? "overdue" : "ready"} />
            },
            { accessorKey: "conclusion", header: "Заключение", cell: ({ row }) => row.original.conclusion || "—" }
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по сотруднику, типу, заключению"
          caption="Реестр медицинских осмотров"
        />
      ) : null}
    </div>
  );
};

export default MedicalPage;
