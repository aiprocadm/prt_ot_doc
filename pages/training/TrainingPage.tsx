import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const programs = [
  { title: "Работы на высоте", group: "Группа 2", status: "Идет обучение", participants: 24 },
  { title: "Пожарно-технический минимум", group: "Группа 1", status: "Назначено", participants: 18 },
  { title: "Электробезопасность", group: "Группа 3", status: "Завершено", participants: 30 }
];

const TrainingPage = () => (
  <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Обучение и инструктажи" }]} />
      <div className="flex gap-2">
        <Button>Назначить обучение</Button>
        <Button variant="outline">Создать инструктаж</Button>
      </div>
    </div>
    <Tabs defaultValue="registry">
      <TabsList>
        <TabsTrigger value="registry">Реестр</TabsTrigger>
        <TabsTrigger value="calendar">Календарь</TabsTrigger>
        <TabsTrigger value="certs">Удостоверения</TabsTrigger>
      </TabsList>
      <TabsContent value="registry">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Программы обучения</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Программа</TableHead>
                  <TableHead>Группа</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Участники</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {programs.map((program) => (
                  <TableRow key={program.title}>
                    <TableCell className="font-medium">{program.title}</TableCell>
                    <TableCell>{program.group}</TableCell>
                    <TableCell>{program.status}</TableCell>
                    <TableCell>{program.participants}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </TabsContent>
      <TabsContent value="calendar">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Календарный план-график</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            План-график отображает дату, преподавателя и аудиторию. В MVP используйте табличный вид.
          </CardContent>
        </Card>
      </TabsContent>
      <TabsContent value="certs">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Удостоверения сотрудников</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Доступны QR-удостоверения и выгрузка PDF для мобильного доступа.
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  </div>
);

export default TrainingPage;
