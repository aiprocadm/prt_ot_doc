import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SyncConflictHelpPage() {
  return (
    <div className="space-y-6 p-6">
      <Breadcrumb items={[{ label: "Настройки", to: "/settings" }, { label: "Синхронизация и конфликты" }]} />
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Офлайн и конфликты синхронизации</h1>
        <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
          Краткий сценарий для полевых клиентов (Wave 4 / mobile PWA): что делать при расхождении версий после
          возврата сети.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Рекомендованный порядок действий</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <ol className="list-decimal space-y-2 pl-5">
            <li>Откройте экран с ошибкой синхронизации и зафиксируйте correlation_id из сообщения (если есть).</li>
            <li>Сравните локальную копию с серверной: приоритет у подтверждённой серверной версии, если политика тенанта не задаёт иное.</li>
            <li>При неразрешимом конфликте создайте задачу в разделе «Задачи» с приложением скриншота и ID сущности.</li>
            <li>Повторите отправку после устранения конфликта; избегайте двойных отправок — используйте idempotent ключи там, где API это поддерживает.</li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
