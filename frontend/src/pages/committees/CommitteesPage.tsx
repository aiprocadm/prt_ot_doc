import { useCallback, useEffect, useState } from "react";

import { committeesApi, type Committee, type Meeting, type Protocol } from "@/api/committees";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

// ── Committee list panel ────────────────────────────────────────────────────

interface CommitteeListProps {
  selected: Committee | null;
  onSelect: (c: Committee) => void;
}

const CommitteeList = ({ selected, onSelect }: CommitteeListProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [items, setItems] = useState<Committee[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await committeesApi.list();
      setItems(page.items);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить комитеты" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Комитеты</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка комитетов" /> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="Нет данных" description="Комитеты ещё не созданы." />
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Название</TableHead>
                <TableHead>Вид</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((c) => (
                <TableRow
                  key={c.id}
                  className={`cursor-pointer ${selected?.id === c.id ? "bg-muted" : ""}`}
                  onClick={() => onSelect(c)}
                >
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell className="text-muted-foreground">{c.kind}</TableCell>
                  <TableCell>
                    <Badge variant={c.is_active ? "default" : "secondary"}>
                      {c.is_active ? "Активен" : "Неактивен"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Meeting list panel ──────────────────────────────────────────────────────

interface MeetingListProps {
  committee: Committee;
  selected: Meeting | null;
  onSelect: (m: Meeting) => void;
}

const MeetingList = ({ committee, selected, onSelect }: MeetingListProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [items, setItems] = useState<Meeting[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await committeesApi.listMeetings(committee.id);
      setItems(page.items);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить заседания" });
    } finally {
      setLoading(false);
    }
  }, [committee.id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Заседания — {committee.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка заседаний" /> : null}
        {!loading && !error && items.length === 0 ? (
          <EmptyState title="Нет данных" description="Заседания ещё не проводились." />
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата</TableHead>
                <TableHead>Место</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((m) => (
                <TableRow
                  key={m.id}
                  className={`cursor-pointer ${selected?.id === m.id ? "bg-muted" : ""}`}
                  onClick={() => onSelect(m)}
                >
                  <TableCell className="font-medium">{formatDate(m.scheduled_at)}</TableCell>
                  <TableCell className="text-muted-foreground">{m.location ?? "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{m.status}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Protocol panel ──────────────────────────────────────────────────────────

interface ProtocolPanelProps {
  meeting: Meeting;
}

const ProtocolPanel = ({ meeting }: ProtocolPanelProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [protocol, setProtocol] = useState<Protocol | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await committeesApi.getProtocol(meeting.id);
      setProtocol(data);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить протокол" });
    } finally {
      setLoading(false);
    }
  }, [meeting.id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Протокол — {formatDate(meeting.scheduled_at)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка протокола" /> : null}
        {!loading && !error && protocol !== null && protocol.decisions.length === 0 ? (
          <EmptyState title="Нет данных" description="Решения по заседанию ещё не внесены." />
        ) : null}
        {!loading && !error && protocol !== null && protocol.decisions.length > 0 ? (
          <div className="space-y-4">
            {protocol.decisions.map(({ decision, tasks }) => (
              <div key={decision.id} className="rounded-md border border-border p-4 space-y-3">
                <p className="text-sm font-medium">{decision.text}</p>
                {decision.decided_at ? (
                  <p className="text-xs text-muted-foreground">Принято: {formatDate(decision.decided_at)}</p>
                ) : null}
                {tasks.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Срок</TableHead>
                        <TableHead>Статус</TableHead>
                        <TableHead>Примечание</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tasks.map((task) => (
                        <TableRow key={task.id}>
                          <TableCell>
                            <span className="flex items-center gap-2">
                              {formatDate(task.due_date)}
                              {task.is_overdue ? (
                                <Badge variant="destructive" className="text-xs">
                                  Просрочено
                                </Badge>
                              ) : null}
                            </span>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{task.status}</Badge>
                          </TableCell>
                          <TableCell className="text-muted-foreground">{task.evidence_note ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-xs text-muted-foreground">Задачи не назначены.</p>
                )}
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Page ────────────────────────────────────────────────────────────────────

const CommitteesPage = () => {
  const [selectedCommittee, setSelectedCommittee] = useState<Committee | null>(null);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);

  const handleSelectCommittee = (c: Committee) => {
    setSelectedCommittee(c);
    setSelectedMeeting(null);
  };

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Комитеты"
        description="Комитеты по охране труда: заседания и протоколы решений."
      />
      <CommitteeList selected={selectedCommittee} onSelect={handleSelectCommittee} />
      {selectedCommittee !== null ? (
        <MeetingList
          committee={selectedCommittee}
          selected={selectedMeeting}
          onSelect={setSelectedMeeting}
        />
      ) : null}
      {selectedMeeting !== null ? <ProtocolPanel meeting={selectedMeeting} /> : null}
    </div>
  );
};

export default CommitteesPage;
