import { useCallback, useMemo, useState } from "react";

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

  const psych = useAsyncResource({
    loader: useCallback(() => operationsApi.getPsychiatricSnapshot(), []),
    initialData: { activityTypes: [], contingent: [] },
    errorMessage: "Не удалось загрузить психиатрическое освидетельствование"
  });
  const [seeding, setSeeding] = useState(false);

  const onSeed = useCallback(async () => {
    setSeeding(true);
    try {
      await operationsApi.seedPsychiatricDefaults();
      await psych.reload();
    } finally {
      setSeeding(false);
    }
  }, [psych]);

  const items = useMemo(
    () => data.exams.map((exam) => ({ ...exam, person: data.persons.find((person) => person.id === exam.person_id) })),
    [data]
  );
  const registry = useLocalRegistry({
    items,
    match: (item, query) => [item.person?.full_name, item.exam_type, item.conclusion].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Медосмотры и допуски"
        description="Реестр использует эндпоинт `/medical/exams` и связывает его с людьми и обязательствами."
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
            { id: "state", header: "Состояние", cell: ({ row }) => <StatusBadge status={new Date(row.original.valid_until) < new Date() ? "overdue" : "ready"} /> },
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

      <section className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Психиатрическое освидетельствование (342н)</h2>
            <p className="text-sm text-muted-foreground">Виды деятельности по перечню ПП РФ № 695 и подлежащий контингент.</p>
          </div>
          {psych.data.activityTypes.length === 0 ? (
            <button
              type="button"
              className="rounded-md border border-border px-3 py-1.5 text-sm"
              onClick={() => void onSeed()}
              disabled={seeding}
            >
              {seeding ? "Загрузка…" : "Загрузить стандартный список 695"}
            </button>
          ) : null}
        </div>
        <ErrorState error={psych.error ?? undefined} onRetry={() => void psych.reload()} />
        {psych.data.activityTypes.length > 0 ? (
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {psych.data.activityTypes.map((a) => (
              <li key={a.id} className="flex justify-between gap-2 border-b border-border/50 py-1">
                <span>{a.name}</span>
                <span className="text-muted-foreground">{Math.round(a.interval_days / 365)} лет</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Каталог видов деятельности пуст.</p>
        )}
        <div className="text-sm">
          Подлежит освидетельствованию (контингент): <strong>{psych.data.contingent.length}</strong>
        </div>
      </section>
    </div>
  );
};

export default MedicalPage;
