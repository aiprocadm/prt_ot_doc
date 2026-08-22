import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/EmptyState";
import { PERMISSIONS } from "@/permissions/permissions";
import type { WorkflowDefinition } from "@/features/workflow/types";

type Props = {
  loading: boolean;
  hasError: boolean;
  definitions: WorkflowDefinition[];
  onStart: (code: string) => void;
  onPublish: (versionId: string) => void;
  onArchive: (versionId: string) => void;
};

export const WorkflowDefinitionsCard = ({
  loading,
  hasError,
  definitions,
  onStart,
  onPublish,
  onArchive,
}: Props) => (
  <Card>
    <CardHeader>
      <CardTitle>Процессы и версии</CardTitle>
    </CardHeader>
    <CardContent className="space-y-4">
      {!loading && !hasError && definitions.length === 0 ? (
        <EmptyState
          title="Нет описаний процессов"
          description="Создайте черновик процесса, чтобы опубликовать первую схему."
        />
      ) : null}
      {definitions.map((definition) => (
        <div key={definition.id} className="rounded-lg border p-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-medium">{definition.name}</div>
              <div className="text-sm text-muted-foreground">
                {definition.code} · сущность: {definition.entity_type}
              </div>
            </div>
            <Can permission={PERMISSIONS.WORKFLOW_MANAGE}>
              {/* Кнопка в повторяющейся строке — вторичная (UX-бюджет:
                  primary на экране одна, у композера). */}
              <Button
                size="sm"
                variant="outline"
                onClick={() => onStart(definition.code)}
              >
                Запустить
              </Button>
            </Can>
          </div>
          {definition.versions.map((version) => (
            <div key={version.id} className="rounded border bg-muted/30 p-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium">
                  Версия {version.version_no}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase text-muted-foreground">
                    {version.status}
                  </span>
                  {version.status !== "published" ? (
                    <Can permission={PERMISSIONS.WORKFLOW_MANAGE}>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onPublish(version.id)}
                      >
                        Опубликовать
                      </Button>
                    </Can>
                  ) : null}
                  {version.status !== "archived" ? (
                    <Can permission={PERMISSIONS.WORKFLOW_MANAGE}>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onArchive(version.id)}
                      >
                        В архив
                      </Button>
                    </Can>
                  ) : null}
                </div>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <div>
                  <div className="text-xs font-medium uppercase text-muted-foreground">
                    Узлы
                  </div>
                  <ul className="mt-1 text-sm space-y-1">
                    {(version.graph_json.nodes ?? []).map((node) => (
                      <li key={node.id}>
                        {node.id} · {node.type} · {node.name ?? "—"}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="text-xs font-medium uppercase text-muted-foreground">
                    Переходы
                  </div>
                  <ul className="mt-1 text-sm space-y-1">
                    {(version.graph_json.transitions ?? []).map(
                      (item, index) => (
                        <li key={`${item.from}-${item.to}-${index}`}>
                          {item.from} → {item.to}
                          {item.when ? ` (${item.when})` : ""}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </CardContent>
  </Card>
);
