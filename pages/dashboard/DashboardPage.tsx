import { CalendarClock, FileText, Layers, ShieldAlert, Users2 } from "lucide-react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RiskBadge } from "@/components/common/RiskBadge";
import { SlaIndicator } from "@/components/common/SlaIndicator";
import { StatusBadge } from "@/components/common/StatusBadge";

const kpis = [
  { label: "Просрочки обучений", value: 12, trend: "+3 за неделю", icon: CalendarClock },
  { label: "Документы ЭДО в работе", value: 48, trend: "7 на подписи", icon: FileText },
  { label: "Топ-риски на объектах", value: 9, trend: "2 критичных", icon: ShieldAlert },
  { label: "СИЗ к замене", value: 34, trend: "в течение 30 дней", icon: Users2 },
  { label: "Мероприятия CAPA", value: 21, trend: "5 на контроле", icon: Layers }
];

const tasks = [
  { id: "TSK-1024", title: "Согласование пакета проверки Ростехнадзора", owner: "Иванова О.А.", sla: "overdue", label: "Просрочено 2 д" },
  { id: "TSK-1031", title: "Назначить обучение по высоте", owner: "Петров И.М.", sla: "warning", label: "До дедлайна 6 ч" },
  { id: "TSK-1045", title: "Подписание договора на СИЗ", owner: "Кузнецов А.А.", sla: "ok", label: "До дедлайна 3 д" }
];

const documents = [
  { id: "DOC-223", title: "Положение о ПБ филиал Урал", status: "processing", route: "Согласование", risk: "medium" },
  { id: "DOC-245", title: "Журнал инструктажей по ОТ", status: "ready", route: "Подписан", risk: "low" },
  { id: "DOC-268", title: "План мероприятий CAPA", status: "draft", route: "Черновик", risk: "high" }
];

export const DashboardPage = () => (
  <div className="space-y-6">
    <div className="flex flex-col gap-2">
      <Breadcrumb items={[{ label: "Главная" }]} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Единый рабочий стол ОТ/ПБ</h1>
          <p className="text-sm text-muted-foreground">
            Контроль задач, ЭДО, рисков и готовности к проверкам по текущему тенанту.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button>Создать документ</Button>
          <Button variant="outline">Запустить мастер</Button>
        </div>
      </div>
    </div>

    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {kpis.map((item) => (
        <Card key={item.label}>
          <CardContent className="space-y-3 py-6">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{item.label}</span>
              <item.icon className="h-4 w-4" />
            </div>
            <div className="text-2xl font-semibold">{item.value}</div>
            <div className="text-xs text-muted-foreground">{item.trend}</div>
          </CardContent>
        </Card>
      ))}
    </div>

    <Tabs defaultValue="tasks">
      <TabsList>
        <TabsTrigger value="tasks">Единый inbox задач</TabsTrigger>
        <TabsTrigger value="documents">ЭДО-реестр</TabsTrigger>
        <TabsTrigger value="readiness">Готовность к проверке</TabsTrigger>
      </TabsList>
      <TabsContent value="tasks">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Задачи и SLA</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Задача</TableHead>
                  <TableHead>Ответственный</TableHead>
                  <TableHead>SLA</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell className="font-medium">{task.id}</TableCell>
                    <TableCell>{task.title}</TableCell>
                    <TableCell>{task.owner}</TableCell>
                    <TableCell>
                      <SlaIndicator status={task.sla as "ok" | "warning" | "overdue"} label={task.label} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </TabsContent>
      <TabsContent value="documents">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Документы и маршруты</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Документ</TableHead>
                  <TableHead>Маршрут</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Риск</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell className="font-medium">{doc.id}</TableCell>
                    <TableCell>{doc.title}</TableCell>
                    <TableCell>{doc.route}</TableCell>
                    <TableCell>
                      <StatusBadge status={doc.status} />
                    </TableCell>
                    <TableCell>
                      <RiskBadge level={doc.risk} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </TabsContent>
      <TabsContent value="readiness">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Пакеты проверки</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="rounded-md border bg-muted/30 p-4">
              <div className="text-sm font-semibold">Ростехнадзор · Плановая</div>
              <p className="mt-1 text-xs text-muted-foreground">
                24 документа, 3 просрочены, 2 без подписи, 1 не отправлен.
              </p>
              <div className="mt-3 flex gap-2">
                <Button size="sm">Сформировать пакет</Button>
                <Button size="sm" variant="outline">
                  Открыть чек-лист
                </Button>
              </div>
            </div>
            <div className="rounded-md border bg-muted/30 p-4">
              <div className="text-sm font-semibold">МЧС · Внеплановая</div>
              <p className="mt-1 text-xs text-muted-foreground">16 документов, нет 2 актов учений.</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="outline">
                  Заполнить пробелы
                </Button>
                <Button size="sm" variant="ghost">
                  История
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  </div>
);

export default DashboardPage;
