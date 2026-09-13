import { useCallback, useState } from "react";
import { Can } from "@/components/permissions/Can";
import { PERMISSIONS } from "@/permissions/permissions";
import { Link } from "react-router-dom";

import { fireSafetyApi } from "@/api/fireSafety";
import { operationsApi } from "@/api/operations";
import { sitesApi } from "@/api/sites";
import { EmptyState } from "@/components/common/EmptyState";
import { deniedNotice } from "@/api/partial";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FireDrillFormDialog } from "@/features/fire-safety/FireDrillFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

/**
 * Тренировки и инструктажи ПБ (Доп. №1 разд. 54.1).
 *
 * ДО этого среза экран назывался «инструктажи и учения», а учений не показывал
 * ни одного: сущности тренировки в платформе не было — только шаблон документа
 * «Программа практической тренировки по эвакуации». Название обещало то, чего
 * экран не делал; теперь план-график и протоколы тренировок — первая секция.
 */

/** Статус тренировки словами: «overdue» человеку ничего не говорит. */
const DRILL_STATUS_TITLES: Record<string, string> = {
  planned: "Запланирована",
  held: "Проведена",
  overdue: "Просрочена",
};

const FireTrainingPage = () => {
  // Секции ПО ОДНОЙ (прецедент экрана средств ПБ и склада): иначе экран растёт
  // таблицами и «тренировки» тонут среди карточек инструктажей.
  const [section, setSection] = useState<"drills" | "briefings">("drills");

  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getFireTrainingSnapshot(), []),
    initialData: {
      denied: [],
      templates: [],
      journals: [],
      overdueEntries: [],
      programs: [],
    },
    errorMessage: "Не удалось загрузить журналы и инструктажи",
  });

  const drills = useAsyncResource({
    loader: useCallback(
      async () => ({
        items: await fireSafetyApi.listDrills(),
        readiness: await fireSafetyApi.readiness(),
        // Площадки — ядровой справочник: тренировку привязывают выбором,
        // а не вводом id (срез-104).
        sites: (await sitesApi.list()).items,
      }),
      [],
    ),
    initialData: {
      items: [],
      sites: [],
      readiness: {
        incidents_open: 0,
        total_units: 0,
        overdue_recharge: 0,
        overdue_inspection: 0,
        due_soon: 0,
        due_soon_days: 30,
        overdue_fire_briefings: 0,
        fire_documents: 0,
        overdue_documents: 0,
        units_without_maintenance: 0,
        overdue_drills: 0,
        planned_drills: 0,
        last_drill_on: null,
        days_since_last_drill: null,
      },
    },
    errorMessage: "Не удалось загрузить тренировки",
  });

  const drillRegistry = useLocalRegistry({
    items: drills.data.items,
    match: (item, query) =>
      [item.title, item.kind_label, item.scenario, item.findings]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
  });

  const { readiness } = drills.data;
  const overdueBriefings = data.overdueEntries.length;
  const blockers = overdueBriefings + readiness.overdue_drills;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Пожарная безопасность · тренировки и инструктажи"
        description="План-график тренировок по эвакуации с протоколами и анализом, а также журналы и шаблоны противопожарных инструктажей."
        actions={
          <Button asChild variant="outline">
            <Link to="/briefings">Открыть инструктажи</Link>
          </Button>
        }
        stats={[
          { label: "Тренировок в плане", value: readiness.planned_drills },
          { label: "Просрочено тренировок", value: readiness.overdue_drills },
          {
            label: "Последняя тренировка",
            value: readiness.last_drill_on
              ? formatDate(readiness.last_drill_on)
              : "не проводилась",
          },
          { label: "Просрочено инструктажей", value: overdueBriefings },
          { label: "Журналы", value: data.journals.length },
        ]}
      />

      {blockers > 0 ? (
        <Card className="border-orange-200 bg-orange-50/40">
          <CardHeader>
            <CardTitle className="text-base">
              Блокеры и дальнейшие действия
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {readiness.overdue_drills > 0 ? (
              <p>
                Тренировок с прошедшим сроком плана и без протокола:{" "}
                {readiness.overdue_drills}. Проведите тренировку и внесите
                протокол либо перенесите дату в плане-графике.
              </p>
            ) : null}
            {overdueBriefings > 0 ? (
              <p>
                Найдено просроченных записей инструктажей: {overdueBriefings}.
                Требуется закрыть задолженность до следующей волны проверок.
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline">
                <Link to="/briefings">Открыть журналы инструктажей</Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/tasks?type=briefing">Открыть связанные задачи</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["drills", "Тренировки и учения"],
            ["briefings", "Инструктажи"],
          ] as const
        ).map(([key, label]) => (
          <Button
            key={key}
            size="sm"
            variant={section === key ? "secondary" : "outline"}
            onClick={() => setSection(key)}
          >
            {label}
          </Button>
        ))}
      </div>

      {section === "drills" ? (
        <>
          <ErrorState
            error={drills.error ?? undefined}
            onRetry={() => void drills.reload()}
          />
          {deniedNotice(data.denied) ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-600/50 dark:bg-amber-950/30 dark:text-amber-50">
              {deniedNotice(data.denied)}
            </p>
          ) : null}
          {drills.loading ? (
            <LoadingScreen label="Загрузка тренировок" />
          ) : null}
          {/*
            ГРАНИЦА, названная НА ЭКРАНЕ (прецедент карточки площадки 360°):
            интервал «не реже раза в полгода» обязателен для объектов с
            массовым пребыванием людей, а признака массового пребывания у
            площадки в данных нет. Поэтому платформа сообщает факт — когда была
            последняя тренировка, — но не объявляет нарушение по интервалу.
          */}
          {!drills.loading && !drills.error ? (
            <p className="text-sm text-muted-foreground">
              {readiness.last_drill_on
                ? `Последняя тренировка проведена ${formatDate(readiness.last_drill_on)}` +
                  (readiness.days_since_last_drill != null
                    ? ` — ${readiness.days_since_last_drill} дн. назад.`
                    : ".")
                : "Проведённых тренировок пока нет."}{" "}
              Требование ППР РФ «не реже одного раза в полгода» относится к
              объектам с массовым пребыванием людей: применимость определяет
              специалист, платформа сама нарушением это не называет.
            </p>
          ) : null}
          {/*
            Срез-104: ручки тренировок (срез-4) работали только через API —
            экран звал «заведите тренировку по эвакуации», а завести её было
            негде. Одна главная кнопка на секцию; протокол вносится правкой
            той же формой.
          */}
          {!drills.loading && !drills.error ? (
            <div>
              <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                <FireDrillFormDialog
                  sites={drills.data.sites}
                  onSubmitted={() => void drills.reload()}
                  trigger={<Button>Запланировать тренировку</Button>}
                />
              </Can>
            </div>
          ) : null}
          {!drills.loading && !drills.error && drillRegistry.total === 0 ? (
            <EmptyState
              title="Тренировки не запланированы"
              description="Заведите тренировку по эвакуации — дата плана попадёт в контроль сроков, а после проведения останется протокол с результатом и анализом."
            />
          ) : null}
          {!drills.loading && !drills.error && drillRegistry.total > 0 ? (
            <RegistryTable
              columns={[
                { accessorKey: "title", header: "Тренировка" },
                {
                  accessorKey: "kind_label",
                  header: "Вид",
                  cell: ({ row }) => row.original.kind_label,
                },
                {
                  accessorKey: "planned_on",
                  header: "По плану",
                  cell: ({ row }) => formatDate(row.original.planned_on),
                },
                {
                  accessorKey: "status",
                  header: "Состояние",
                  cell: ({ row }) =>
                    DRILL_STATUS_TITLES[row.original.status] ??
                    row.original.status,
                },
                {
                  accessorKey: "outcome_label",
                  header: "Результат",
                  cell: ({ row }) =>
                    row.original.held_on
                      ? `${formatDate(row.original.held_on)} · ${
                          row.original.outcome_label ?? "—"
                        }`
                      : "—",
                },
                {
                  id: "actions",
                  header: "Действия",
                  // Правка и внесение протокола — одна и та же форма: пока
                  // тренировка не проведена, протокольная часть свёрнута.
                  cell: ({ row }) => (
                    <Can permission={PERMISSIONS.FIRE_SAFETY_MANAGE}>
                      <FireDrillFormDialog
                        sites={drills.data.sites}
                        initialData={row.original}
                        onSubmitted={() => void drills.reload()}
                        trigger={
                          <Button variant="ghost" size="sm">
                            {row.original.held_on ? "Изменить" : "Протокол"}
                          </Button>
                        }
                      />
                    </Can>
                  ),
                },
              ]}
              data={drillRegistry.pagedItems}
              pageIndex={drillRegistry.pageIndex}
              pageSize={drillRegistry.pageSize}
              total={drillRegistry.total}
              onPageChange={drillRegistry.onPageChange}
              onPageSizeChange={drillRegistry.onPageSizeChange}
              onSearchChange={drillRegistry.onSearchChange}
              searchPlaceholder="Поиск по названию, виду, сценарию"
              caption="План-график тренировок и учений"
            />
          ) : null}
        </>
      ) : (
        <>
          <ErrorState
            error={error ?? undefined}
            onRetry={() => void reload()}
          />
          {loading ? <LoadingScreen label="Загрузка журналов" /> : null}
          {!loading &&
          !error &&
          data.templates.length + data.journals.length === 0 ? (
            <EmptyState
              title="Нет данных по инструктажам"
              description="Создайте шаблоны или журналы инструктажей."
            />
          ) : null}
          {!loading && !error ? (
            <div className="grid gap-4 lg:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Шаблоны</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {data.templates.slice(0, 5).map((item) => (
                    <p key={item.id}>
                      {item.title} · {item.status}
                    </p>
                  ))}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Журналы</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {data.journals.slice(0, 5).map((item) => (
                    <p key={item.id}>
                      {item.title} · {item.status}
                    </p>
                  ))}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Просроченные записи
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {data.overdueEntries.slice(0, 5).map((item) => (
                    <p key={item.id}>
                      {item.briefing_type} · {item.status}
                    </p>
                  ))}
                </CardContent>
              </Card>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
};

export default FireTrainingPage;
