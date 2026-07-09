import { useCallback, useMemo, useState } from "react";

import {
  operationsApi,
  type ContingentRegisterRowDto,
  type MedicalSummaryDto,
  type NamedListRowDto
} from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const EXAM_KIND_LABELS: Record<string, string> = {
  periodic: "Периодический",
  preliminary: "Предварительный",
  psychiatric: "Психиатрическое (342н)",
  fluorography: "Флюорография",
  health_book: "Медкнижка"
};

const examKindLabel = (kind: string) => EXAM_KIND_LABELS[kind] ?? kind;

const mutationErrorText = (err: unknown, fallback: string) =>
  (err as { message?: string })?.message ?? fallback;

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

  const oversight = useAsyncResource({
    loader: useCallback(() => operationsApi.getMedicalOversightSnapshot(), []),
    initialData: {
      summary: null as MedicalSummaryDto | null,
      register: [] as ContingentRegisterRowDto[],
      namedList: [] as NamedListRowDto[]
    },
    errorMessage: "Не удалось загрузить контингент медосмотров"
  });

  const [contingentView, setContingentView] = useState<"register" | "named">("register");
  const [printError, setPrintError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  const onPrint = useCallback(
    async (fmt: "docx" | "pdf") => {
      setPrinting(true);
      setPrintError(null);
      try {
        if (contingentView === "register") {
          await operationsApi.downloadContingentRegisterPrint(fmt);
        } else {
          await operationsApi.downloadNamedListPrint(fmt);
        }
      } catch (err) {
        setPrintError(mutationErrorText(err, "Не удалось сформировать печатную форму"));
      } finally {
        setPrinting(false);
      }
    },
    [contingentView]
  );

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
          { label: "Позиций контингента", value: oversight.data.summary?.total ?? "—" },
          { label: "Просрочено/отсутствует", value: oversight.data.summary?.overdue_count ?? "—" },
          { label: "Активных отстранений", value: oversight.data.summary?.suspended_count ?? "—" }
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Контингент медосмотров</h2>
            <p className="text-sm text-muted-foreground">Реестр по должностям (29н/342н) и поимённый список; печатные формы DOCX/PDF.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={`rounded-md border px-3 py-1.5 text-sm ${contingentView === "register" ? "border-primary font-medium" : "border-border"}`}
              onClick={() => setContingentView("register")}
            >
              По должностям
            </button>
            <button
              type="button"
              className={`rounded-md border px-3 py-1.5 text-sm ${contingentView === "named" ? "border-primary font-medium" : "border-border"}`}
              onClick={() => setContingentView("named")}
            >
              Поимённый список
            </button>
            <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm" onClick={() => void onPrint("docx")} disabled={printing}>
              DOCX
            </button>
            <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm" onClick={() => void onPrint("pdf")} disabled={printing}>
              PDF
            </button>
          </div>
        </div>
        <ErrorState error={oversight.error ?? undefined} onRetry={() => void oversight.reload()} />
        {printError ? <p className="text-sm text-destructive">{printError}</p> : null}
        {contingentView === "register" ? (
          oversight.data.register.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Должность</TableHead>
                  <TableHead>Численность</TableHead>
                  <TableHead>Факторы</TableHead>
                  <TableHead>Виды осмотров</TableHead>
                  <TableHead>Периодичность, мес</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {oversight.data.register.map((row) => (
                  <TableRow key={row.position_id}>
                    <TableCell>{row.position_name}</TableCell>
                    <TableCell>{row.headcount}</TableCell>
                    <TableCell>{row.factors.map((f) => `${f.code} — ${f.name}`).join(", ") || "—"}</TableCell>
                    <TableCell>{row.exam_kinds.map(examKindLabel).join(", ")}</TableCell>
                    <TableCell>{row.periodicity_months ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">Контингент пуст — настройте нормы и факторы.</p>
          )
        ) : oversight.data.namedList.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ФИО</TableHead>
                <TableHead>Должность</TableHead>
                <TableHead>Подразделение</TableHead>
                <TableHead>Виды осмотров</TableHead>
                <TableHead>Последний осмотр</TableHead>
                <TableHead>Следующий</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {oversight.data.namedList.map((row) => (
                <TableRow key={row.person_id}>
                  <TableCell>{row.full_name}</TableCell>
                  <TableCell>{row.position_name ?? "—"}</TableCell>
                  <TableCell>{row.department ?? "—"}</TableCell>
                  <TableCell>{row.required_kinds.map(examKindLabel).join(", ")}</TableCell>
                  <TableCell>{row.last_exam_date ? formatDate(row.last_exam_date) : "—"}</TableCell>
                  <TableCell>{row.next_due_date ? formatDate(row.next_due_date) : "—"}</TableCell>
                  <TableCell>
                    <StatusBadge status={row.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">Поимённый список пуст.</p>
        )}
      </section>

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
