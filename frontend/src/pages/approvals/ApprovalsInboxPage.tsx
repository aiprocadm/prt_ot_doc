import { useEffect, useState } from "react";

import { approvalsApi, type ApprovalProcess, type ApprovalTask } from "@/api/approvals";
import { edoApi, type EdoEnvelope } from "@/api/edo";
import { signApi, type SignatureRequest } from "@/api/sign";
import ApprovalTaskCard from "@/components/ApprovalTaskCard";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ApiError } from "@/types/dto/common";

const ApprovalsInboxPage = () => {
  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [doneTasks, setDoneTasks] = useState<ApprovalTask[]>([]);
  const [processes, setProcesses] = useState<ApprovalProcess[]>([]);
  const [edos, setEdos] = useState<EdoEnvelope[]>([]);
  const [signatures, setSignatures] = useState<SignatureRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [openTasks, closed, list, edoItems, signItems] = await Promise.all([
        approvalsApi.listMyTasks("open"),
        approvalsApi.listMyTasks("done"),
        approvalsApi.listProcesses(),
        edoApi.list(),
        signApi.list(),
      ]);
      setTasks(openTasks);
      setDoneTasks(closed);
      setProcesses(list);
      setEdos(edoItems);
      setSignatures(signItems);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить данные согласований" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "ЭДО / Согласования" }]} />
        <Button variant="outline" onClick={() => void load()}>Обновить</Button>
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка согласований" /> : null}

      <Tabs defaultValue="my-tasks">
        <TabsList>
          <TabsTrigger value="my-tasks">
            Мои задачи {tasks.length > 0 && <span className="ml-1 rounded-full bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">{tasks.length}</span>}
          </TabsTrigger>
          <TabsTrigger value="routes">Маршруты ({processes.length})</TabsTrigger>
          <TabsTrigger value="signatures">Подписи ({signatures.length})</TabsTrigger>
          <TabsTrigger value="edo">ЭДО ({edos.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="my-tasks" className="space-y-4 pt-4">
          {!loading && tasks.length === 0 ? (
            <EmptyState
              title="Открытых задач нет"
              description="Все задачи согласования выполнены или вам ещё не назначены новые."
            />
          ) : (
            <div className="space-y-3">
              {tasks.map((task) => (
                <ApprovalTaskCard key={task.id} task={task} onChanged={() => void load()} />
              ))}
            </div>
          )}
          {doneTasks.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-semibold text-muted-foreground">
                  Выполненные задачи ({doneTasks.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {doneTasks.slice(0, 5).map((task) => (
                    <div key={task.id} className="flex items-center justify-between rounded border bg-muted/30 p-2 text-sm">
                      <span className="text-muted-foreground">#{task.id.slice(0, 8)} — задача</span>
                      <StatusBadge status={task.status} />
                    </div>
                  ))}
                  {doneTasks.length > 5 && (
                    <div className="text-xs text-muted-foreground">…и ещё {doneTasks.length - 5}</div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="routes" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Маршруты согласования</CardTitle>
            </CardHeader>
            <CardContent>
              {!loading && processes.length === 0 ? (
                <EmptyState title="Активных маршрутов нет" description="Запустите согласование документа, чтобы создать маршрут." />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Объект</TableHead>
                      <TableHead>Шаг</TableHead>
                      <TableHead>Статус</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {processes.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="font-medium">#{p.id.slice(0, 8)}</TableCell>
                        <TableCell>{p.object_id}</TableCell>
                        <TableCell>{p.current_step}</TableCell>
                        <TableCell><StatusBadge status={p.status} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="signatures" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Запросы на подпись</CardTitle>
            </CardHeader>
            <CardContent>
              {!loading && signatures.length === 0 ? (
                <EmptyState title="Запросов на подпись нет" description="Активных запросов КЭП/УКЭП нет." />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Провайдер</TableHead>
                      <TableHead>Дата</TableHead>
                      <TableHead>Статус</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {signatures.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="font-medium">#{s.id.slice(0, 8)}</TableCell>
                        <TableCell>{s.provider}</TableCell>
                        <TableCell>—</TableCell>
                        <TableCell><StatusBadge status={s.status} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="edo" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Конверты ЭДО</CardTitle>
            </CardHeader>
            <CardContent>
              {!loading && edos.length === 0 ? (
                <EmptyState title="Конвертов ЭДО нет" description="Активных конвертов в системе ЭДО нет." />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Внешний ID</TableHead>
                      <TableHead>Дата</TableHead>
                      <TableHead>Статус</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {edos.map((e) => (
                      <TableRow key={e.id}>
                        <TableCell className="font-medium">#{e.id.slice(0, 8)}</TableCell>
                        <TableCell>{e.external_id ?? "—"}</TableCell>
                        <TableCell>—</TableCell>
                        <TableCell><StatusBadge status={e.status} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ApprovalsInboxPage;
