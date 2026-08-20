import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { sitesApi, type SiteOverview } from "@/api/sites";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { lightLabel, lightVariant } from "@/lib/lights";
import type { ApiError } from "@/types/dto/common";

/**
 * Карточка площадки 360° (BIZ-54-57 срез-3, Доп. №1 разд. 57.1).
 *
 * ТЗ: «на одном экране — обязательства и статус по ВСЕМ применимым
 * дисциплинам, а не отдельные экраны на каждую». Приёмка §58.3 повторяет то же
 * отдельной строкой.
 *
 * Три блока (бюджет разд. 59.2 — до шести): о площадке, дисциплины, границы.
 * Блоки помечены `data-ux-block`, иначе измеритель бюджета не увидел бы их
 * вовсе и проверка «блоков не больше шести» была бы пустой.
 */

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

const SiteCardPage = () => {
  const { siteId = "" } = useParams();
  const [overview, setOverview] = useState<SiteOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const load = useCallback(async () => {
    if (!siteId) return;
    setLoading(true);
    setError(null);
    setForbidden(false);
    try {
      setOverview(await sitesApi.overview(siteId));
    } catch (err) {
      const apiError = asApiError(err, "Не удалось загрузить карточку площадки");
      // 403 объясняем словами: площадки читает администратор арендатора.
      // Голая ошибка на этом месте выглядит как поломка, а не как правило.
      if (apiError.status === 403) setForbidden(true);
      else setError(apiError);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    void load();
  }, [load]);

  const facts = overview?.facts;
  const permits = facts?.permits;

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title={overview?.name ?? "Карточка площадки"}
        description="Статус площадки по всем дисциплинам сразу: медосмотры, СИЗ, обучение, ПБ, ПромБез и остальные."
      />
      <div>
        <Link
          to="/sites"
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
        >
          ← К списку площадок
        </Link>
      </div>

      {forbidden ? (
        <EmptyState
          title="Доступ только у администратора"
          description="Площадки и их карточки читает администратор арендатора."
        />
      ) : (
        <>
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка карточки площадки" /> : null}

          {!loading && !error && overview ? (
            <>
              <section data-ux-block>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">
                      О площадке
                      <Badge
                        className="ml-2"
                        variant={lightVariant(overview.overall)}
                      >
                        {lightLabel(overview.overall)}
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div
                      className="flex flex-wrap gap-4 text-sm"
                      data-testid="site-facts"
                    >
                      <span>
                        Адрес: <strong>{overview.address || "не указан"}</strong>
                      </span>
                      <span>
                        Класс опасности:{" "}
                        <strong>{overview.hazard_class || "не указан"}</strong>
                      </span>
                      <span>
                        ОПО:{" "}
                        <strong>
                          {overview.is_hazardous_production_facility
                            ? overview.opo_register_number || "да, без номера"
                            : "нет"}
                        </strong>
                      </span>
                      <span>
                        Рабочих мест: <strong>{facts?.workplaces ?? 0}</strong>
                      </span>
                      <span>
                        Сотрудников на площадке:{" "}
                        <strong>{facts?.people ?? 0}</strong>
                      </span>
                      <span data-testid="people-without-workplace">
                        Без рабочего места во всей компании (ни к одной
                        площадке не отнесены):{" "}
                        <strong>{facts?.people_without_workplace ?? 0}</strong>
                      </span>
                      <span data-testid="site-permits">
                        Действующих нарядов-допусков:{" "}
                        <strong>{permits?.total ?? 0}</strong>
                        {permits && permits.without_discipline > 0
                          ? ` (без дисциплины: ${permits.without_discipline} — ` +
                            `${permits.without_discipline_titles.join(", ")}; ` +
                            `${permits.without_discipline_reason})`
                          : null}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </section>

              <section data-ux-block>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">
                      Дисциплины ({overview.disciplines.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="disciplines">
                      <thead>
                        <tr className="text-left text-muted-foreground">
                          <th className="py-1 pr-4 font-medium">Дисциплина</th>
                          <th className="py-1 pr-4 font-medium">Состояние</th>
                          <th className="py-1 font-medium">Расшифровка</th>
                        </tr>
                      </thead>
                      <tbody>
                        {overview.disciplines.map((row) => (
                          <tr
                            key={row.discipline}
                            className="border-t align-top"
                          >
                            <td className="py-2 pr-4">{row.title}</td>
                            <td className="py-2 pr-4">
                              <Badge variant={lightVariant(row.light)}>
                                {lightLabel(row.light)}
                              </Badge>
                            </td>
                            <td className="py-2 text-muted-foreground">
                              {row.reason}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
              </section>

              <section data-ux-block>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">
                      Что к площадке привязано, но здесь не посчитано
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul
                      className="space-y-1 text-sm text-muted-foreground"
                      data-testid="not-counted"
                    >
                      {overview.not_counted.map((row) => (
                        <li key={row.title}>
                          <strong className="text-foreground">
                            {row.title}
                          </strong>{" "}
                          — {row.reason}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              </section>
            </>
          ) : null}
        </>
      )}
    </div>
  );
};

export default SiteCardPage;
