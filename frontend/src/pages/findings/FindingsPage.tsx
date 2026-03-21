import { useEffect, useMemo, useState } from "react";

import { opsApi, type FindingDto } from "@/api/ops";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const FindingsPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<FindingDto[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await opsApi.getFindings());
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить findings" });
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
      [item.id, item.title, item.status, item.severity, item.source_type, item.finding_type, item.description]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    );
  }, [items, query]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Findings"
        description="Tenant-aware operational registry backed by backend `/findings`, with real severity/status/source projections instead of demo rows."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Открытые, подтверждённые и закрытые findings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Поиск по title, source, severity, status" value={query} onChange={(event) => setQuery(event.target.value)} />
          <ErrorState error={error ?? undefined} onRetry={load} />
          {loading ? <LoadingScreen label="Загрузка findings" /> : null}
          {!loading && !error && filtered.length === 0 ? (
            <EmptyState title="Findings не найдены" description={query ? "Измените строку поиска." : "В текущем tenant пока нет findings."} />
          ) : null}
          {!loading && !error && filtered.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Finding</TableHead>
                  <TableHead>Источник</TableHead>
                  <TableHead>Срок</TableHead>
                  <TableHead>Критичность</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((finding) => (
                  <TableRow key={finding.id}>
                    <TableCell className="font-medium">{finding.id.slice(0, 8)}</TableCell>
                    <TableCell>
                      <div className="font-medium">{finding.title}</div>
                      <div className="text-xs text-muted-foreground">{finding.finding_type}</div>
                    </TableCell>
                    <TableCell>
                      <div>{finding.source_type}</div>
                      <div className="text-xs text-muted-foreground">{finding.source_id.slice(0, 8)}</div>
                    </TableCell>
                    <TableCell>{formatDate(finding.due_date) || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={finding.severity === "critical" ? "destructive" : "secondary"}>{finding.severity}</Badge>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={finding.status} />
                    </TableCell>
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

export default FindingsPage;
