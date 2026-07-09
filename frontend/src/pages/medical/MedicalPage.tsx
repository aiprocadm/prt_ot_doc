import { useCallback, useMemo, useState } from "react";

import {
  operationsApi,
  type ContingentRegisterRowDto,
  type MedicalReferralDto,
  type MedicalSummaryDto,
  type MedicalSuspensionDto,
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

const SUSPENSION_REASON_LABELS: Record<string, string> = {
  unfit: "Негоден",
  contraindication: "Противопоказания"
};

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

  const [referralStatusFilter, setReferralStatusFilter] = useState("");
  const referrals = useAsyncResource({
    loader: useCallback(
      () => operationsApi.listMedicalReferrals(referralStatusFilter ? { status: referralStatusFilter } : undefined),
      [referralStatusFilter]
    ),
    initialData: [] as MedicalReferralDto[],
    errorMessage: "Не удалось загрузить направления"
  });
  const [referralError, setReferralError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generatedCount, setGeneratedCount] = useState<number | null>(null);
  const [creatingReferral, setCreatingReferral] = useState(false);
  const [newReferral, setNewReferral] = useState({ person_id: "", exam_kind: "periodic", due_at: "", medical_org_name: "" });
  const [transitioning, setTransitioning] = useState<ReadonlySet<string>>(new Set());
  const [completingId, setCompletingId] = useState<string | null>(null);
  const [resultExamId, setResultExamId] = useState("");

  const personName = useMemo(() => {
    const map = new Map<string, string>();
    data.persons.forEach((person) => map.set(person.id, person.full_name));
    return (id: string) => map.get(id) ?? id;
  }, [data.persons]);

  const onGenerateReferrals = useCallback(async () => {
    setGenerating(true);
    setReferralError(null);
    setGeneratedCount(null);
    try {
      const { count } = await operationsApi.generateMedicalReferrals();
      setGeneratedCount(count);
      await referrals.reload();
    } catch (err) {
      setReferralError(mutationErrorText(err, "Не удалось сформировать направления"));
    } finally {
      setGenerating(false);
    }
  }, [referrals]);

  const onCreateReferral = useCallback(async () => {
    if (!newReferral.person_id) return;
    setCreatingReferral(true);
    setReferralError(null);
    setGeneratedCount(null);
    try {
      await operationsApi.createMedicalReferral({
        person_id: newReferral.person_id,
        exam_kind: newReferral.exam_kind,
        ...(newReferral.due_at ? { due_at: newReferral.due_at } : {}),
        ...(newReferral.medical_org_name.trim() ? { medical_org_name: newReferral.medical_org_name.trim() } : {})
      });
      setNewReferral({ person_id: "", exam_kind: "periodic", due_at: "", medical_org_name: "" });
      await referrals.reload();
    } catch (err) {
      setReferralError(mutationErrorText(err, "Не удалось создать направление"));
    } finally {
      setCreatingReferral(false);
    }
  }, [newReferral, referrals]);

  const onTransitionReferral = useCallback(
    async (referralId: string, to: string, resultExam?: string) => {
      setTransitioning((prev) => {
        const next = new Set(prev);
        next.add(referralId);
        return next;
      });
      setReferralError(null);
      setGeneratedCount(null);
      try {
        await operationsApi.transitionMedicalReferral(referralId, {
          to,
          ...(resultExam ? { result_exam_id: resultExam } : {})
        });
        setCompletingId(null);
        setResultExamId("");
        await referrals.reload();
      } catch (err) {
        setReferralError(mutationErrorText(err, "Не удалось изменить статус направления"));
      } finally {
        setTransitioning((prev) => {
          const next = new Set(prev);
          next.delete(referralId);
          return next;
        });
      }
    },
    [referrals]
  );

  const [suspensionsActiveOnly, setSuspensionsActiveOnly] = useState(true);
  const suspensions = useAsyncResource({
    loader: useCallback(
      () => operationsApi.listMedicalSuspensions(suspensionsActiveOnly ? { status: "active" } : undefined),
      [suspensionsActiveOnly]
    ),
    initialData: [] as MedicalSuspensionDto[],
    errorMessage: "Не удалось загрузить отстранения"
  });
  const [suspensionError, setSuspensionError] = useState<string | null>(null);
  const [liftingId, setLiftingId] = useState<string | null>(null);

  const examLabelById = useMemo(() => {
    const map = new Map<string, string>();
    data.exams.forEach((exam) => map.set(exam.id, `${examKindLabel(exam.exam_type)} · ${formatDate(exam.exam_date)}`));
    return (id: string | null | undefined) => (id ? map.get(id) ?? id : "—");
  }, [data.exams]);

  const onLiftSuspension = useCallback(
    async (suspensionId: string) => {
      if (!window.confirm("Снять отстранение? Работник будет допущен к работе.")) return;
      setLiftingId(suspensionId);
      setSuspensionError(null);
      try {
        await operationsApi.liftMedicalSuspension(suspensionId);
        await Promise.all([suspensions.reload(), oversight.reload()]);
      } catch (err) {
        setSuspensionError(mutationErrorText(err, "Не удалось снять отстранение"));
      } finally {
        setLiftingId(null);
      }
    },
    [oversight, suspensions]
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
              aria-pressed={contingentView === "register"}
              className={`rounded-md border px-3 py-1.5 text-sm ${contingentView === "register" ? "border-primary font-medium" : "border-border"}`}
              onClick={() => {
                setPrintError(null);
                setContingentView("register");
              }}
            >
              По должностям
            </button>
            <button
              type="button"
              aria-pressed={contingentView === "named"}
              className={`rounded-md border px-3 py-1.5 text-sm ${contingentView === "named" ? "border-primary font-medium" : "border-border"}`}
              onClick={() => {
                setPrintError(null);
                setContingentView("named");
              }}
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
        {printError ? <p role="alert" className="text-sm text-destructive">{printError}</p> : null}
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Направления на медосмотры</h2>
            <p className="text-sm text-muted-foreground">Выдача направлений вручную или по контингенту; статусы: выдан → запланирован → завершён/отменён.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Фильтр по статусу направления"
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={referralStatusFilter}
              onChange={(e) => setReferralStatusFilter(e.target.value)}
            >
              <option value="">Все статусы</option>
              <option value="issued">Выданные</option>
              <option value="scheduled">Запланированные</option>
              <option value="completed">Завершённые</option>
              <option value="cancelled">Отменённые</option>
            </select>
            <button
              type="button"
              className="rounded-md border border-border px-3 py-1.5 text-sm"
              onClick={() => void onGenerateReferrals()}
              disabled={generating}
            >
              {generating ? "Формирование…" : "Сформировать по контингенту"}
            </button>
          </div>
        </div>
        <ErrorState error={referrals.error ?? undefined} onRetry={() => void referrals.reload()} />
        {referralError ? <p role="alert" className="text-sm text-destructive">{referralError}</p> : null}
        {generatedCount !== null ? <p className="text-sm">Создано направлений: {generatedCount}</p> : null}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <select
            aria-label="Сотрудник для направления"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.person_id}
            onChange={(e) => setNewReferral((f) => ({ ...f, person_id: e.target.value }))}
          >
            <option value="">Сотрудник…</option>
            {data.persons.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
          <select
            aria-label="Вид осмотра"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.exam_kind}
            onChange={(e) => setNewReferral((f) => ({ ...f, exam_kind: e.target.value }))}
          >
            {Object.entries(EXAM_KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input
            aria-label="Срок направления"
            type="date"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.due_at}
            onChange={(e) => setNewReferral((f) => ({ ...f, due_at: e.target.value }))}
          />
          <input
            aria-label="Медорганизация"
            placeholder="Медорганизация (опционально)"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.medical_org_name}
            onChange={(e) => setNewReferral((f) => ({ ...f, medical_org_name: e.target.value }))}
          />
        </div>
        <button
          type="button"
          className="rounded-md border border-border px-3 py-1.5 text-sm"
          onClick={() => void onCreateReferral()}
          disabled={creatingReferral || !newReferral.person_id}
        >
          Создать направление
        </button>
        {referrals.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Сотрудник</TableHead>
                <TableHead>Вид</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Срок</TableHead>
                <TableHead>Медорганизация</TableHead>
                <TableHead>Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {referrals.data.map((referral) => (
                <TableRow key={referral.id}>
                  <TableCell>{personName(referral.person_id)}</TableCell>
                  <TableCell>{examKindLabel(referral.exam_kind)}</TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1">
                      <StatusBadge status={referral.status} />
                      {referral.is_overdue && referral.status !== "completed" && referral.status !== "cancelled" ? (
                        <span className="text-xs text-destructive">Просрочено</span>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell>{referral.due_at ? formatDate(referral.due_at) : "—"}</TableCell>
                  <TableCell>{referral.medical_org_name ?? "—"}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      {referral.status === "issued" ? (
                        <button
                          type="button"
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => void onTransitionReferral(referral.id, "scheduled")}
                          disabled={transitioning.has(referral.id)}
                        >
                          Запланировать
                        </button>
                      ) : null}
                      {referral.status === "scheduled" ? (
                        <button
                          type="button"
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => {
                            setCompletingId((current) => (current === referral.id ? null : referral.id));
                            setResultExamId("");
                          }}
                          disabled={transitioning.has(referral.id)}
                        >
                          Завершить
                        </button>
                      ) : null}
                      {referral.status === "issued" || referral.status === "scheduled" ? (
                        <button
                          type="button"
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => void onTransitionReferral(referral.id, "cancelled")}
                          disabled={transitioning.has(referral.id)}
                        >
                          Отменить
                        </button>
                      ) : null}
                    </div>
                    {completingId === referral.id ? (
                      (() => {
                        const personExams = data.exams.filter((exam) => exam.person_id === referral.person_id);
                        if (personExams.length === 0) {
                          return <p className="mt-2 text-xs text-muted-foreground">Сначала зафиксируйте осмотр в реестре выше.</p>;
                        }
                        return (
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <select
                              aria-label="Осмотр-результат"
                              className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                              value={resultExamId}
                              onChange={(e) => setResultExamId(e.target.value)}
                            >
                              <option value="">Выберите осмотр…</option>
                              {personExams.map((exam) => (
                                <option key={exam.id} value={exam.id}>
                                  {examKindLabel(exam.exam_type)} · {formatDate(exam.exam_date)}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              className="rounded-md border border-border px-2 py-1 text-xs"
                              onClick={() => void onTransitionReferral(referral.id, "completed", resultExamId)}
                              disabled={!resultExamId || transitioning.has(referral.id)}
                            >
                              Подтвердить
                            </button>
                          </div>
                        );
                      })()
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : !referrals.loading ? (
          <p className="text-sm text-muted-foreground">Направлений нет.</p>
        ) : null}
      </section>

      <section className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Отстранения от работы</h2>
            <p className="text-sm text-muted-foreground">Автоматические отстранения по результатам осмотров; снятие — только admin/owner.</p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              aria-label="Только активные"
              type="checkbox"
              checked={suspensionsActiveOnly}
              onChange={(e) => setSuspensionsActiveOnly(e.target.checked)}
            />
            Только активные
          </label>
        </div>
        <ErrorState error={suspensions.error ?? undefined} onRetry={() => void suspensions.reload()} />
        {suspensionError ? <p role="alert" className="text-sm text-destructive">{suspensionError}</p> : null}
        {suspensions.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Сотрудник</TableHead>
                <TableHead>Причина</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Осмотр-источник</TableHead>
                <TableHead>Действие</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suspensions.data.map((suspension) => (
                <TableRow key={suspension.id}>
                  <TableCell>{personName(suspension.person_id)}</TableCell>
                  <TableCell>{SUSPENSION_REASON_LABELS[suspension.reason] ?? suspension.reason}</TableCell>
                  <TableCell>
                    <StatusBadge status={suspension.status} />
                  </TableCell>
                  <TableCell>{examLabelById(suspension.source_exam_id)}</TableCell>
                  <TableCell>
                    {suspension.status === "active" ? (
                      <button
                        type="button"
                        className="rounded-md border border-border px-2 py-1 text-xs"
                        onClick={() => void onLiftSuspension(suspension.id)}
                        disabled={liftingId === suspension.id}
                      >
                        Снять отстранение
                      </button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : !suspensions.loading ? (
          <p className="text-sm text-muted-foreground">Отстранений нет.</p>
        ) : null}
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
