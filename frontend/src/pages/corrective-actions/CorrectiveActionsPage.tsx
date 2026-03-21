import { useEffect, useMemo, useState } from "react";

import { opsApi, type CorrectiveActionDto } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const CorrectiveActionsPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<CorrectiveActionDto[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await opsApi.getCorrectiveActions());
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить CAPA" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) =>
      [item.id, item.title, item.status, item.source_type, item.action_type, item.effectiveness_status, item.description]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    );
  }, [items, query]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Корректирующие действия"
        description="Операционный CAPA-реестр на основе backend `/corrective-actions` с реальными due/status/effectiveness полями."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Корректирующие и предупреждающие действия</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Поиск по мероприятию, source, status" value={query} onChange={(event) => setQuery(event.target.value)} />
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка CAPA" /> : null}
          {!loading && !error && filtered.length === 0 ? (
            <EmptyState title="Действия не найдены" description={query ? "Попробуйте другой запрос." : "В текущем tenant пока нет корректирующих действий."} />
          ) : null}
          {!loading && !error && filtered.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Мероприятие</TableHead>
                  <TableHead>Источник</TableHead>
                  <TableHead>Срок</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Эффективность</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((action) => (
                  <TableRow key={action.id}>
                    <TableCell className="font-medium">{action.id.slice(0, 8)}</TableCell>
                    <TableCell>
                      <div className="font-medium">{action.title}</div>
                      <div className="text-xs text-muted-foreground">{action.action_type}</div>
                    </TableCell>
                    <TableCell>
                      <div>{action.source_type}</div>
                      <div className="text-xs text-muted-foreground">{action.source_id.slice(0, 8)}</div>
                    </TableCell>
                    <TableCell>{formatDate(action.due_date) || "—"}</TableCell>
                    <TableCell>
                      <StatusBadge status={action.status} />
                    </TableCell>
                    <TableCell>{action.effectiveness_status ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default CorrectiveActionsPage;
