import { useCallback, useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { privacyApi, type BreachStage, type PdnBreachDto } from "@/api/privacy";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Утечки персональных данных и сроки уведомления (152-ФЗ разд. 66.3, срез-208).
 *
 * ЗАЧЕМ ЭКРАН. Срез-207 завёл реестр и сроки, но только ручками: пользоваться
 * этим не мог никто, кроме того, кто умеет звать API. Обязательство, которое
 * нельзя выполнить через продукт, не выполняется вовсе.
 *
 * ЧТО ЗДЕСЬ ГЛАВНОЕ:
 *
 * 1. **Честная строка о том, чего платформа НЕ делает.** Она наверху и не
 *    прячется: уведомление в Роскомнадзор подают через форму регулятора, и
 *    человек должен понять это раньше, чем решит, что всё сделано за него.
 * 2. **Часы, а не дни.** Срок приходит с сервера в часах; показывать «через 1
 *    день» значило бы потерять те часы, ради которых всё и затевалось.
 * 3. **Три шага отмечаются по отдельности** — тремя кнопками, а не одной.
 */

const TONE: Record<string, string> = {
  overdue: "border-l-4 border-rose-500 bg-rose-50",
  pending: "border-l-4 border-amber-500 bg-amber-50",
  done: "border-l-4 border-emerald-500 bg-emerald-50",
  no_deadline: "border-l-4 border-slate-300 bg-muted",
};

const formatMoment = (value: string | null): string => {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("ru-RU");
};

const PrivacyBreachesPage = () => {
  const [items, setItems] = useState<PdnBreachDto[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [summary, setSummary] = useState("");
  const [discoveredAt, setDiscoveredAt] = useState("");
  const [affected, setAffected] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await privacyApi.breaches();
      setItems(data.items ?? []);
      setNotice(data.notice ?? "");
    } catch {
      toast.error("Не удалось загрузить реестр утечек");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await privacyApi.registerBreach({
        summary: summary.trim(),
        // Момент обнаружения вводит ЧЕЛОВЕК: платформа не знает, когда
        // организации сообщили об утечке, а от этого момента идёт срок.
        discovered_at: new Date(discoveredAt).toISOString(),
        affected_people: affected ? Number(affected) : null,
      });
      toast.success("Утечка зарегистрирована, срок пошёл");
      setSummary("");
      setDiscoveredAt("");
      setAffected("");
      await load();
    } catch {
      toast.error("Не удалось зарегистрировать утечку");
    } finally {
      setSaving(false);
    }
  };

  const markStep = async (breachId: string, stage: BreachStage) => {
    try {
      await privacyApi.markBreachStep(breachId, stage);
      await load();
    } catch {
      toast.error("Не удалось отметить шаг");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Утечки персональных данных</h1>
        <p className="text-sm text-muted-foreground">
          Сроки уведомления по 152-ФЗ: 24 часа на сообщение в Роскомнадзор, 72
          часа на результаты расследования — от момента обнаружения.
        </p>
      </div>

      {/* Строка о том, чего платформа НЕ делает, стоит НАВЕРХУ и не прячется:
          иначе экран читается как «мы уведомим за вас». */}
      {notice ? (
        <p
          className="rounded border border-amber-300 bg-amber-50 p-3 text-sm"
          data-testid="privacy-breach-notice"
        >
          {notice}
        </p>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Зарегистрировать утечку</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4 md:grid-cols-2"
            onSubmit={(event) => void submit(event)}
          >
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="breach-summary">Что случилось</Label>
              <Input
                id="breach-summary"
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="breach-discovered">Когда обнаружили</Label>
              <Input
                id="breach-discovered"
                type="datetime-local"
                value={discoveredAt}
                onChange={(event) => setDiscoveredAt(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="breach-affected">Сколько человек затронуто</Label>
              <Input
                id="breach-affected"
                type="number"
                min={0}
                value={affected}
                onChange={(event) => setAffected(event.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? "Сохранение..." : "Зарегистрировать"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {loading ? <LoadingScreen label="Загрузка реестра утечек" /> : null}
      {!loading && items.length === 0 ? (
        <EmptyState
          title="Утечек не зарегистрировано"
          description="Здесь появятся утечки персональных данных и сроки уведомления по 152-ФЗ."
        />
      ) : null}

      <div className="space-y-4">
        {items.map((item) => (
          <Card key={item.id} data-testid="privacy-breach">
            <CardHeader>
              <CardTitle className="text-base">{item.summary}</CardTitle>
              <div className="text-sm text-muted-foreground">
                Обнаружено: {formatMoment(item.discovered_at)}
                {item.affected_people != null
                  ? ` · затронуто человек: ${item.affected_people}`
                  : null}
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {item.deadlines.map((deadline) => (
                <div
                  key={deadline.stage}
                  className={`rounded p-3 text-sm ${TONE[deadline.status] ?? ""}`}
                  data-testid="privacy-breach-deadline"
                  data-status={deadline.status}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{deadline.title}</span>
                    {/* Подпись состояния приходит с сервера. */}
                    <span className="text-xs uppercase">
                      {deadline.status_title}
                    </span>
                    {/* ЧАСЫ, а не дни: «через 1 день» потеряло бы то, ради
                        чего срок и считается. */}
                    {deadline.hours_left != null ? (
                      <span className="text-xs">
                        осталось часов: {deadline.hours_left}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Срок: {formatMoment(deadline.due_at)} · Выполнено:{" "}
                    {formatMoment(deadline.done_at)}
                  </div>
                  {deadline.status !== "done" ? (
                    // Три шага отмечаются ПО ОТДЕЛЬНОСТИ — три кнопки, а не
                    // одна: закон требует всех трёх, и они разные.
                    <Button
                      className="mt-2"
                      variant="outline"
                      size="sm"
                      onClick={() => void markStep(item.id, deadline.stage)}
                    >
                      Отметить выполненным
                    </Button>
                  ) : null}
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default PrivacyBreachesPage;
