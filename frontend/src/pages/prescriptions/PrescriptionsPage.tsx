import { useEffect, useMemo, useState } from "react";

import { opsApi, type PrescriptionDto } from "@/api/ops";
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

const PrescriptionsPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PrescriptionDto[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await opsApi.getPrescriptions());
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить предписания" });
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
    return items.filter((item) => [item.id, item.description, item.status, item.inspection_id, item.incident_id].filter(Boolean).join(" ").toLowerCase().includes(normalized));
  }, [items, query]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Предписания"
        description="Операционный реестр предписаний из backend `/prescriptions` с tenant-aware фильтрацией и статусами."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Открытые и закрытые предписания</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Поиск по описанию, inspection_id, incident_id" value={query} onChange={(event) => setQuery(event.target.value)} />
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка предписаний" /> : null}
          {!loading && !error && filtered.length === 0 ? (
            <EmptyState title="Предписания не найдены" description={query ? "Измените запрос поиска." : "В этом tenant пока нет предписаний."} />
          ) : null}
          {!loading && !error && filtered.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Описание</TableHead>
                  <TableHead>Источник</TableHead>
                  <TableHead>Срок</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.id.slice(0, 8)}</TableCell>
                    <TableCell>{item.description}</TableCell>
                    <TableCell>{item.incident_id ? `Incident ${item.incident_id.slice(0, 8)}` : `Inspection ${item.inspection_id.slice(0, 8)}`}</TableCell>
                    <TableCell>{formatDate(item.due_at) || "—"}</TableCell>
                    <TableCell><StatusBadge status={item.status} /></TableCell>
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

export default PrescriptionsPage;
