import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { bulkActionPipelineRuns, listPipelineRuns, type PipelineRun } from "@/api/pipelines";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { useAsyncResource } from "@/hooks/useAsyncResource";

const PipelineRuns = () => {
  const { data: runs, loading, error, reload } = useAsyncResource({
    loader: listPipelineRuns,
    initialData: [] as PipelineRun[],
    errorMessage: "Не удалось загрузить историю пайплайнов",
  });
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (runs.length === 0) {
      setSelected({});
    }
  }, [runs]);

  const selectedIds = useMemo(() => Object.entries(selected).filter(([, on]) => on).map(([id]) => id), [selected]);

  const toggleAll = (checked: boolean) => {
    const next: Record<string, boolean> = {};
    for (const run of runs) next[run.run_id] = checked;
    setSelected(next);
  };

  const doBulk = async (action: "retry" | "cancel") => {
    if (selectedIds.length === 0) return;
    await bulkActionPipelineRuns(selectedIds, action);
    await reload();
  };

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Пайплайны / История задач</h1>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка истории пайплайнов" /> : null}
      {!loading && !error && runs.length === 0 ? (
        <EmptyState title="Пайплайны не найдены" description="После первых запусков пайплайна здесь появится история задач." />
      ) : null}
      <div className="flex items-center gap-2 text-sm">
        <button className="rounded border px-3 py-1" onClick={() => doBulk("retry").catch(() => undefined)} disabled={!selectedIds.length}>Повторить выбранные</button>
        <button className="rounded border px-3 py-1" onClick={() => doBulk("cancel").catch(() => undefined)} disabled={!selectedIds.length}>Отменить выбранные</button>
      </div>
      <div className="rounded border">
        <label className="flex items-center gap-2 border-b p-3 text-xs text-muted-foreground">
          <input type="checkbox" checked={runs.length > 0 && selectedIds.length === runs.length} onChange={(e) => toggleAll(e.target.checked)} />
          Выбрать все
        </label>
        {runs.map((run) => (
          <div key={run.run_id} className="flex items-center justify-between border-b p-3 text-sm last:border-b-0">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={Boolean(selected[run.run_id])}
                onChange={(e) => setSelected((prev) => ({ ...prev, [run.run_id]: e.target.checked }))}
              />
              <Link to={`/pipelines/runs/${run.run_id}`} className="hover:underline">{run.run_id}</Link>
            </label>
            <span>{run.status}</span>
          </div>
        ))}
      </div>
    </section>
  );
};

export default PipelineRuns;
