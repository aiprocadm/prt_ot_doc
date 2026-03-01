import { PipelineStepRun } from "@/api/pipelines";

const badgeClass = (status: string) => {
  if (status === "success") return "bg-emerald-100 text-emerald-800";
  if (status === "failed") return "bg-red-100 text-red-800";
  if (status === "running") return "bg-blue-100 text-blue-800";
  if (status === "canceled") return "bg-zinc-200 text-zinc-700";
  return "bg-amber-100 text-amber-800";
};

const durationText = (started?: string | null, ended?: string | null) => {
  if (!started || !ended) return "—";
  const ms = new Date(ended).getTime() - new Date(started).getTime();
  return `${Math.max(0, Math.round(ms / 1000))} c`;
};

const stringify = (data: unknown) => {
  if (!data || (typeof data === "object" && Object.keys(data as Record<string, unknown>).length === 0)) return null;
  return JSON.stringify(data, null, 2);
};

export const JobTimeline = ({ steps }: { steps: PipelineStepRun[] }) => (
  <div className="space-y-2">
    {steps.map((step) => (
      <div key={step.step_run_id} className="space-y-2 rounded border p-3 text-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">{step.step_code}</div>
            <div className="text-xs text-muted-foreground">attempt: {step.attempt}</div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`rounded px-2 py-0.5 text-xs ${badgeClass(step.status)}`}>{step.status}</span>
            <span className="text-xs text-muted-foreground">{durationText(step.started_at, step.ended_at)}</span>
          </div>
        </div>
        {step.error_code ? <div className="text-xs text-red-600">{step.error_code}</div> : null}
        {step.error_payload ? <pre className="overflow-auto rounded bg-red-50 p-2 text-[11px] text-red-800">{stringify(step.error_payload)}</pre> : null}
        {(step as { output?: unknown }).output ? <pre className="overflow-auto rounded bg-muted/40 p-2 text-[11px]">{stringify((step as { output?: unknown }).output)}</pre> : null}
      </div>
    ))}
  </div>
);
