import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { cancelPipelineRun, getPipelineRun, retryPipelineRun, retryPipelineStepRun, type PipelineRun } from "@/api/pipelines";
import { JobTimeline } from "@/components/JobTimeline";
import { FileList } from "@/features/files/FileList";

const PipelineRunDetails = () => {
  const { id = "" } = useParams();
  const [run, setRun] = useState<PipelineRun | null>(null);

  const load = () => getPipelineRun(id).then(setRun);

  useEffect(() => {
    load().catch(() => setRun(null));
  }, [id]);

  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) return;
    const t = setInterval(() => {
      load().catch(() => undefined);
    }, 3000);
    return () => clearInterval(t);
  }, [run]);

  const failedStep = useMemo(() => run?.step_runs.find((s) => s.status === "failed"), [run]);

  const stepLogs = useMemo(() => run?.logs ?? [], [run]);

  if (!run) return <section>Загрузка...</section>;

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Job {run.run_id}</h1>
      <div className="flex gap-2">
        <button className="rounded border px-3 py-1" onClick={() => retryPipelineRun(run.run_id).then(setRun)}>Retry failed</button>
        {failedStep ? (
          <button className="rounded border px-3 py-1" onClick={() => retryPipelineStepRun(run.run_id, failedStep.step_run_id).then(setRun)}>Retry step</button>
        ) : null}
        <button className="rounded border px-3 py-1" onClick={() => cancelPipelineRun(run.run_id).then(setRun)}>Cancel</button>
      </div>
      <JobTimeline steps={run.step_runs} />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded border p-3 text-sm">
          <h2 className="mb-2 font-medium">Step logs</h2>
          <div className="max-h-56 space-y-1 overflow-auto">
            {stepLogs.slice(-50).map((log, idx) => (
              <div key={`${log.timestamp}-${idx}`} className="text-xs">
                <span className="text-muted-foreground">[{log.level}]</span> {log.step_name ? `${log.step_name}: ` : ""}{log.message}
              </div>
            ))}
          </div>
        </div>
        <div className="rounded border p-3 text-sm">
          <h2 className="mb-2 font-medium">Artifacts</h2>
          <FileList entityType="job" entityId={run.run_id} />
        </div>
      </div>
    </section>
  );
};

export default PipelineRunDetails;
