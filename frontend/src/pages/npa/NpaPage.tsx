import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { npaApi } from "@/api/npa";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  NpaActFormDialog,
  NpaRevisionFormDialog,
} from "@/features/npa/NpaFormDialogs";
import { NpaTable } from "@/features/npa/NpaTable";
import { ROUTES } from "@/router/routes";
import { useNpaStore } from "@/stores/npa";

type NpaDetail = {
  act: { id: string; code: string; title: string; edition: string };
  revisions: Array<{
    id: string;
    revision_code: string;
    title: string;
    effective_from?: string | null;
    effective_to?: string | null;
    change_summary?: string | null;
  }>;
  bindings: Record<string, string[]>;
  summary: Record<string, number>;
  tasks_to_create: Array<{ code: string; title: string; count: number }>;
};

const NpaPage = () => {
  const { list, setFilters, filters, items, all, loading, error, canManage } =
    useNpaStore();
  const [search, setSearch] = useState(filters.search ?? "");
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
                    {canManage && selectedId ? (
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
                        <div className="font-medium">
                          {revision.revision_code}
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
                </div>
                <div>
                  <div className="text-xs font-medium uppercase text-muted-foreground">
                    Связанные сущности
                  </div>
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    {Object.entries(detail.summary).map(([key, value]) => (
                      <div key={key} className="rounded border p-3 text-sm">
                        {key}: <span className="font-medium">{value}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 grid gap-3">
                    {Object.entries(detail.bindings).map(([key, values]) => (
                      <div key={key} className="rounded border bg-muted/30 p-3">
                        <div className="text-xs font-medium uppercase text-muted-foreground">
                          {key}
                        </div>
                        <div className="mt-2 text-sm">
                          {values.length ? values.join(", ") : "—"}
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
