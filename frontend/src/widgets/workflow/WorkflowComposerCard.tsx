import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PERMISSIONS } from "@/permissions/permissions";

type Props = {
  newCode: string;
  graphText: string;
  validation: string | null;
  setNewCode: (value: string) => void;
  setGraphText: (value: string) => void;
  onValidate: () => void;
  onCreate: () => void;
  onRefresh: () => void;
};

export const WorkflowComposerCard = ({
  newCode,
  graphText,
  validation,
  setNewCode,
  setGraphText,
  onValidate,
  onCreate,
  onRefresh
}: Props) => (
  <Card>
    <CardHeader><CardTitle>Движок процессов (BPM) v1</CardTitle></CardHeader>
    <CardContent className="space-y-3">
      <div className="grid gap-3 xl:grid-cols-[0.5fr,1fr]">
        <Input value={newCode} onChange={(event) => setNewCode(event.target.value)} placeholder="Код процесса" />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={onValidate}>Проверить граф</Button>
          <Can permission={PERMISSIONS.WORKFLOW_MANAGE}>
            <Button onClick={onCreate}>Создать черновик</Button>
          </Can>
          <Button variant="outline" onClick={onRefresh}>Обновить</Button>
        </div>
      </div>
      <Textarea value={graphText} onChange={(event) => setGraphText(event.target.value)} rows={14} />
      {validation ? <div className="text-sm text-muted-foreground">{validation}</div> : null}
    </CardContent>
  </Card>
);

