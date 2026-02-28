import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const demoEvents = [
  { id: "1", date: "2026-03-20", type: "training", title: "Обучение: продление допуска" },
  { id: "2", date: "2026-03-22", type: "ppe", title: "Срок действия СИЗ" },
  { id: "3", date: "2026-03-23", type: "inspection", title: "Плановая проверка" }
];

const CalendarPage = () => {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Календарь мероприятий</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {demoEvents.map((event) => (
            <div key={event.id} className="rounded border p-3">
              <div className="font-medium">{event.title}</div>
              <div className="text-sm text-muted-foreground">{event.date} · {event.type}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default CalendarPage;
