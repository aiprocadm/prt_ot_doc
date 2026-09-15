import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { npaApi } from "@/api/npa";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NpaBindingDialog } from "@/features/npa/NpaBindingDialog";
import {
  NpaActFormDialog,
  NpaRevisionFormDialog,
} from "@/features/npa/NpaFormDialogs";
import { NpaRevisionCompare } from "@/features/npa/NpaRevisionCompare";
import { NpaTable } from "@/features/npa/NpaTable";
import { ROUTES } from "@/router/routes";
import { useNpaStore } from "@/stores/npa";
import type {
  NpaBindingDto,
  NpaBindingTarget,
  NpaScope,
} from "@/types/dto/npa";

type NpaDetail = {
  act: {
    id: string;
    code: string;
    title: string;
    edition: string;
    // Срез-201: чей это акт. По нему решается, можно ли его переиздать.
    scope?: NpaScope;
    scope_title?: string;
  };
  revisions: Array<{
    id: string;
    revision_code: string;
    title: string;
    effective_from?: string | null;
    effective_to?: string | null;
    change_summary?: string | null;
    /** Срез-198: состояние редакции решает сервер — «Действует», «Ещё не
     * вступила в силу», «Утратила силу», «Перекрыта более поздней». Считать
     * его на витрине значило бы завести второй ответ на вопрос «по чему мы
     * сейчас живём». */
    status?: string;
    status_title?: string;
    /** Срез-202: занесён ли текст этой редакции. Сравнение предлагается только
     * там, где сравнивать есть что, — кнопка, всегда кончающаяся отказом,
     * хуже отсутствующей. */
    has_text?: boolean;
  }>;
  bindings: Record<string, string[]>;
  /** Срез-142: связи по одной, с именами — для списка и кнопки «Отвязать». */
  binding_items?: NpaBindingDto[];
  /** Срез-144: сколько связей не пересмотрено после новой редакции. */
  stale_bindings?: number;
  active_revision_id?: string | null;
  summary: Record<string, number>;
  /** Срез-197: категории влияния, которые платформа записывать не умеет, — с
   * причиной. Раньше они считались вечным нулём и экран их молча скрывал, а
   * человек читал отсутствие строки как «не задевает». */
  unrecorded?: Record<string, string>;
  tasks_to_create: Array<{ code: string; title: string; count: number }>;
};

const BINDING_KIND_LABELS: Record<NpaBindingTarget, string> = {
  document: "Документ",
  template_version: "Версия шаблона",
  pack: "Пакет",
};

const SUMMARY_LABELS: Record<string, string> = {
  documents: "Документы",
  templates: "Версии шаблонов",
  packages: "Пакеты",
  risks: "Риски",
  checklists: "Чек-листы",
  workflows: "Маршруты",
  roles: "Роли",
  sites: "Площадки",
  // Срез-145: активные требования реестра, выведенные из акта.
  requirements: "Требования",
};

const NpaPage = () => {
  const {
    list,
    setFilters,
    filters,
    items,
    all,
    loading,
    error,
    canManage,
    canCreateOwn,
  } = useNpaStore();
  const [search, setSearch] = useState(filters.search ?? "");
  // Срез-142: поиск ведёт сюда ссылкой `/npa?selected=<id>` — выбранный акт
  // берём из адреса, иначе ссылка открывала бы пустую детализацию.
  const [searchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(
    searchParams.get("selected"),
  );
  const [detail, setDetail] = useState<NpaDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    void list();
  }, [list]);

  const loadDetail = useCallback((id: string) => {
    setDetailLoading(true);
    void npaApi
      .getDetail<NpaDetail>(id)
      .then((response) => setDetail(response))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  // Срез-141: сервер список не фильтрует — поиск по коду и названию
  // считается в сторе, поэтому «Применить» не ходит в сеть.
  const applyFilters = () => {
    setFilters({ search: search || undefined });
  };

  const createUpdateTasks = async () => {
    if (!selectedId) return;
    try {
      await npaApi.createImpactTasks(selectedId);
      const response = await npaApi.getDetail<NpaDetail>(selectedId);
      setDetail(response);
      toast.success("Задачи обновления созданы");
    } catch {
      toast.error("Не удалось создать задачи обновления");
    }
  };

  const review = async (binding: NpaBindingDto) => {
    if (!selectedId) return;
    try {
      await npaApi.reviewBinding(selectedId, binding.id);
      toast.success("Связь пересмотрена");
      loadDetail(selectedId);
    } catch {
      toast.error("Не удалось отметить связь пересмотренной");
    }
  };

  const unbind = async (binding: NpaBindingDto) => {
    if (!selectedId) return;
    try {
      await npaApi.deleteBinding(selectedId, binding.id);
      toast.success("Связь снята");
      loadDetail(selectedId);
    } catch {
      toast.error("Не удалось снять связь");
    }
  };

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[{ label: "Главная", to: ROUTES.DASHBOARD }, { label: "НПА" }]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void list()} />
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 py-6">
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium" htmlFor="npa-search">
              Поиск
            </label>
            <Input
              id="npa-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <Button variant="outline" onClick={applyFilters}>
            Применить
          </Button>
          {canManage ? (
            <NpaActFormDialog
              trigger={<Button className="ml-auto">Добавить акт</Button>}
              onCreated={() => void list()}
            />
          ) : null}
          {/* Срез-201: своя нормативка организации. Кнопка отдельная от
              «Добавить акт», потому что поступки разные: тот акт увидят все
              арендаторы, этот — только своя организация. */}
          {canCreateOwn ? (
            <NpaActFormDialog
              scope="own"
              trigger={
                <Button
                  variant="outline"
                  className={canManage ? "" : "ml-auto"}
                >
                  Добавить свой акт
                </Button>
              }
              onCreated={() => void list()}
            />
          ) : null}
        </CardContent>
      </Card>
      {loading && items.length === 0 ? (
        <LoadingScreen label="Загрузка реестра НПА" />
      ) : null}
      {!loading && !error && items.length === 0 ? (
        <EmptyState
          title="НПА не найдены"
          description={
            all.length > 0
              ? "По запросу ничего не найдено — измените поиск."
              : canManage
                ? "Добавьте нормативный акт кнопкой «Добавить акт» — реестр общий для всех арендаторов."
                : canCreateOwn
                  ? "Общий реестр ведёт владелец платформы, а свой приказ по организации вы можете добавить сами — кнопкой «Добавить свой акт»."
                  : "Реестр НПА ведёт владелец платформы; пока в нём нет ни одного акта."
          }
        />
      ) : null}
      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <div className="space-y-3">
          {items.length > 0 ? <NpaTable /> : null}
          <Card>
            <CardHeader>
              <CardTitle>Детализация НПА</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {items.slice(0, 10).map((item) => (
                <Button
                  key={item.id}
                  variant={selectedId === item.id ? "default" : "outline"}
                  className="mr-2 mb-2"
                  onClick={() => setSelectedId(item.id)}
                >
                  {item.code}
                </Button>
              ))}
            </CardContent>
          </Card>
        </div>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Анализ влияния</CardTitle>
            <Button
              variant="outline"
              onClick={() => void createUpdateTasks()}
              disabled={!selectedId}
            >
              Создать задачи обновления
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {detailLoading ? (
              <LoadingScreen label="Загрузка анализа влияния" />
            ) : detail ? (
              <>
                <div>
                  <div className="font-medium">{detail.act.code}</div>
                  <div className="text-sm text-muted-foreground">
                    {detail.act.title} · {detail.act.edition}
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-medium uppercase text-muted-foreground">
                      Редакции
                    </div>
                    {/* Срез-201: редакцию своего акта ведёт сам арендатор —
                        иначе собственный приказ остался бы мёртвой карточкой,
                        которую нельзя переиздать. */}
                    {(canManage || detail.act.scope === "own") && selectedId ? (
                      <NpaRevisionFormDialog
                        actId={selectedId}
                        trigger={
                          <Button variant="outline" size="sm">
                            Добавить редакцию
                          </Button>
                        }
                        onCreated={() => loadDetail(selectedId)}
                      />
                    ) : null}
                  </div>
                  <div className="space-y-2 mt-2">
                    {detail.revisions.map((revision) => (
                      <div key={revision.id} className="rounded border p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {/* Срез-202: у кода редакции появился второй дом —
                              выбор в блоке сравнения. Проверять карточку по
                              простому совпадению текста стало неоднозначно,
                              поэтому у неё есть собственная отметка. */}
                          <span
                            className="font-medium"
                            data-testid="npa-revision-code"
                          >
                            {revision.revision_code}
                          </span>
                          {revision.status_title ? (
                            <span
                              data-testid="npa-revision-status"
                              data-status={revision.status}
                              className={
                                revision.status === "active"
                                  ? "rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800"
                                  : revision.status === "upcoming"
                                    ? "rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800"
                                    : "rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                              }
                            >
                              {revision.status_title}
                            </span>
                          ) : null}
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {revision.title}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {revision.effective_from ?? "—"} →{" "}
                          {revision.effective_to ?? "∞"}
                        </div>
                      </div>
                    ))}
                  </div>
                  {/* Срез-202 (разд. 19.4): «дифф» — предпоследний шаг процесса
                      обновления нормативного контента. Остальные пять шагов
                      были на месте с срезов 141/144/198. */}
                  {selectedId ? (
                    <NpaRevisionCompare
                      actId={selectedId}
                      revisions={detail.revisions}
                    />
                  ) : null}
                </div>
                <div>
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-medium uppercase text-muted-foreground">
                      Связанные сущности
                    </div>
                    {selectedId ? (
                      <NpaBindingDialog
                        actId={selectedId}
                        trigger={
                          <Button variant="outline" size="sm">
                            Привязать документ
                          </Button>
                        }
                        onCreated={() => loadDetail(selectedId)}
                      />
                    ) : null}
                  </div>
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    {Object.entries(detail.summary)
                      .filter(([, value]) => value > 0)
                      .map(([key, value]) => (
                        <div key={key} className="rounded border p-3 text-sm">
                          {SUMMARY_LABELS[key] ?? key}:{" "}
                          <span className="font-medium">{value}</span>
                        </div>
                      ))}
                  </div>
                  {Object.keys(detail.unrecorded ?? {}).length > 0 ? (
                    <div
                      className="mt-2 rounded border border-dashed p-3 text-xs text-muted-foreground"
                      data-testid="npa-unrecorded"
                    >
                      Платформа пока не записывает связи акта с этими
                      сущностями, поэтому по ним нельзя сказать «не задевает»:{" "}
                      {Object.keys(detail.unrecorded ?? {})
                        .map((key) => SUMMARY_LABELS[key] ?? key)
                        .join(", ")}
                      .
                    </div>
                  ) : null}
                  <div className="mt-2 text-sm">
                    <Link
                      className="underline"
                      to={`/npa/requirements?npa_id=${detail.act.id}`}
                      data-testid="npa-requirements-link"
                    >
                      Требования из акта
                      {(detail.summary.requirements ?? 0) > 0
                        ? ` (${detail.summary.requirements})`
                        : ""}
                    </Link>
                  </div>
                  {(detail.stale_bindings ?? 0) > 0 ? (
                    <div
                      className="mt-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm"
                      data-testid="npa-stale-summary"
                    >
                      Требуют пересмотра: {detail.stale_bindings}. В реестре
                      вступила новая редакция — сверьте связанные документы и
                      нажмите «Пересмотрено».
                    </div>
                  ) : null}
                  <div className="mt-3 space-y-2">
                    {(detail.binding_items ?? []).length === 0 ? (
                      <div className="text-sm text-muted-foreground">
                        К акту пока ничего не привязано — оценка влияния
                        считается по связям.
                      </div>
                    ) : null}
                    {(detail.binding_items ?? []).map((binding) => (
                      <div
                        key={binding.id}
                        className="flex items-center justify-between gap-3 rounded border bg-muted/30 p-3"
                      >
                        <div>
                          <div className="text-sm font-medium">
                            {binding.title}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {BINDING_KIND_LABELS[binding.entity_type] ??
                              binding.entity_type}
                            {binding.ref ? ` · ${binding.ref}` : ""}
                            {/* Срез-197: кого и где касается связь. Пустая
                                область означает «весь акт» — отдельное
                                состояние, и приписывать ему слова не надо. */}
                            {Object.values(binding.context ?? {}).length > 0
                              ? ` · ${Object.values(binding.context ?? {}).join(" · ")}`
                              : ""}
                          </div>
                          {binding.stale ? (
                            <div
                              className="text-xs text-amber-700"
                              data-testid="npa-binding-stale"
                            >
                              Не пересмотрена
                              {binding.reviewed_revision_code
                                ? ` (сверяли по ред. ${binding.reviewed_revision_code})`
                                : ""}
                            </div>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-1">
                          {binding.stale ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => void review(binding)}
                            >
                              Пересмотрено
                            </Button>
                          ) : null}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void unbind(binding)}
                          >
                            Отвязать
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-medium uppercase text-muted-foreground">
                    База задач
                  </div>
                  <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">
                    {detail.tasks_to_create.map((task) => (
                      <li key={task.code}>
                        {task.title} · {task.count}
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            ) : (
              <div className="text-sm text-muted-foreground">
                Выберите НПА для просмотра редакций и анализа влияния.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default NpaPage;
