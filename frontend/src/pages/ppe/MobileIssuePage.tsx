import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { useMobileIssue } from "./mobile-issue/useMobileIssue";

const MobileIssuePage = () => {
  const navigate = useNavigate();
  const issue = useMobileIssue();
  const [workerQuery, setWorkerQuery] = useState("");
  const [itemQuery, setItemQuery] = useState("");

  const workerResults = useMemo(() => {
    const q = workerQuery.trim().toLowerCase();
    const base = issue.activePersons;
    if (!q) return base.slice(0, 20);
    return base.filter((p) => `${p.full_name} ${p.position ?? ""}`.toLowerCase().includes(q)).slice(0, 20);
  }, [issue.activePersons, workerQuery]);

  const itemResults = useMemo(() => {
    const q = itemQuery.trim().toLowerCase();
    if (!q) return issue.items.slice(0, 30);
    return issue.items.filter((it) => `${it.name} ${it.code}`.toLowerCase().includes(q)).slice(0, 30);
  }, [issue.items, itemQuery]);

  const cartCount = issue.cart.reduce((sum, line) => sum + line.quantity, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb
          items={[
            { label: "Главная", to: "/dashboard" },
            { label: "СИЗ и склады", to: "/ppe" },
            { label: "Мобильная выдача" }
          ]}
        />
        <Button variant="outline" onClick={() => navigate("/ppe")}>
          К карточкам СИЗ
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Мобильная выдача СИЗ</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ErrorState error={issue.error ?? undefined} onRetry={issue.reload} />
          {issue.loading ? <LoadingScreen label="Загрузка данных выдачи" /> : null}

          {!issue.loading && !issue.error ? (
            <>
              {issue.worker ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/40 p-3">
                  <div>
                    <div className="font-medium">{issue.worker.full_name}</div>
                    <div className="text-sm text-muted-foreground">{issue.worker.position ?? "—"}</div>
                  </div>
                  <Button variant="ghost" onClick={issue.reset}>
                    Сменить сотрудника
                  </Button>
                </div>
              ) : null}

              {issue.step === "worker" ? (
                <section className="space-y-3" aria-label="Выбор сотрудника">
                  <input
                    type="search"
                    className="h-11 w-full rounded-md border px-3 text-base"
                    placeholder="Поиск сотрудника по ФИО или должности"
                    aria-label="Поиск сотрудника"
                    value={workerQuery}
                    onChange={(e) => setWorkerQuery(e.target.value)}
                  />
                  {workerResults.length === 0 ? (
                    <EmptyState title="Сотрудники не найдены" description="Уточните запрос или проверьте справочник сотрудников." />
                  ) : (
                    <ul className="space-y-2">
                      {workerResults.map((person) => (
                        <li key={person.id}>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between rounded-md border p-3 text-left hover:bg-accent"
                            onClick={() => issue.selectWorker(person)}
                          >
                            <span className="font-medium">{person.full_name}</span>
                            <span className="text-sm text-muted-foreground">{person.position ?? "—"}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ) : null}

              {issue.step === "items" ? (
                <section className="space-y-4" aria-label="Выбор СИЗ">
                  <input
                    type="search"
                    className="h-11 w-full rounded-md border px-3 text-base"
                    placeholder="Поиск СИЗ по названию или коду"
                    aria-label="Поиск СИЗ"
                    value={itemQuery}
                    onChange={(e) => setItemQuery(e.target.value)}
                  />
                  <ul className="space-y-2">
                    {itemResults.map((item) => {
                      const onHand = issue.onHandFor(item.id);
                      return (
                        <li key={item.id} className="flex items-center justify-between rounded-md border p-3">
                          <div>
                            <div className="font-medium">{item.name}</div>
                            {issue.stockAware ? (
                              <div className="text-sm text-muted-foreground">На складе: {onHand}</div>
                            ) : null}
                          </div>
                          <Button size="sm" onClick={() => issue.addItem(item)}>
                            + Добавить
                          </Button>
                        </li>
                      );
                    })}
                  </ul>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Корзина ({cartCount})</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {issue.cart.length === 0 ? (
                        <p className="text-sm text-muted-foreground">Добавьте позиции СИЗ для выдачи.</p>
                      ) : (
                        <ul className="space-y-2">
                          {issue.cart.map((line) => {
                            const short = line.on_hand !== null && line.quantity > line.on_hand;
                            return (
                              <li key={line.item_id} className="flex items-center justify-between gap-2 rounded-md border p-2">
                                <div className="min-w-0">
                                  <div className="truncate font-medium">{line.item_name}</div>
                                  {short ? (
                                    <div className="text-sm text-destructive">Больше, чем на складе ({line.on_hand})</div>
                                  ) : null}
                                </div>
                                <div className="flex items-center gap-2">
                                  <Button size="sm" variant="outline" aria-label={`Уменьшить ${line.item_name}`} onClick={() => issue.setQty(line.item_id, line.quantity - 1)}>
                                    −
                                  </Button>
                                  <span className="w-8 text-center" aria-label={`Количество ${line.item_name}`}>
                                    {line.quantity}
                                  </span>
                                  <Button size="sm" variant="outline" aria-label={`Увеличить ${line.item_name}`} onClick={() => issue.setQty(line.item_id, line.quantity + 1)}>
                                    +
                                  </Button>
                                  <Button size="sm" variant="ghost" onClick={() => issue.removeItem(line.item_id)}>
                                    Удалить
                                  </Button>
                                </div>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </CardContent>
                  </Card>

                  <div className="flex justify-between gap-2">
                    <Button variant="ghost" onClick={issue.reset}>
                      Отмена
                    </Button>
                    <Button disabled={issue.cart.length === 0} onClick={() => issue.setStep("review")}>
                      К обзору ({cartCount})
                    </Button>
                  </div>
                </section>
              ) : null}

              {issue.step === "review" ? (
                <section className="space-y-4" aria-label="Обзор и выдача">
                  {issue.allIssued ? (
                    <div className="space-y-3">
                      <div className="rounded-md border border-green-600/40 bg-green-50 p-3 text-green-800">
                        Выдано позиций: {issue.results?.length ?? 0}. Работник: {issue.worker?.full_name}
                      </div>
                      <Button onClick={issue.reset}>Новая выдача</Button>
                    </div>
                  ) : (
                    <>
                      <ul className="space-y-2">
                        {issue.cart.map((line) => (
                          <li key={line.item_id} className="flex items-center justify-between rounded-md border p-3">
                            <span className="font-medium">{line.item_name}</span>
                            <span>× {line.quantity}</span>
                          </li>
                        ))}
                      </ul>
                      {issue.results ? (
                        <ul className="space-y-1" aria-label="Результат выдачи">
                          {issue.results.map((r) => (
                            <li key={r.item_id} className={r.status === "ok" ? "text-green-700" : "text-destructive"}>
                              {r.status === "ok" ? "✓" : "✗"} {r.item_name} × {r.quantity}
                              {r.status === "error" && r.error ? ` — ${r.error}` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="flex justify-between gap-2">
                        <Button variant="ghost" onClick={() => issue.setStep("items")}>
                          Назад
                        </Button>
                        <Button disabled={issue.submitting || issue.cart.length === 0} onClick={() => void issue.issueAll()}>
                          {issue.submitting ? "Выдача…" : `Выдать всё (${cartCount})`}
                        </Button>
                      </div>
                    </>
                  )}
                </section>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default MobileIssuePage;
