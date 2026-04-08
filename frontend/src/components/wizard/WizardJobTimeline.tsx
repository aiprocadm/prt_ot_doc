import { memo } from "react";

import type { PipelineStepRun } from "@/api/pipelines";

const statusClassMap: Record<string, string> = {
  queued: "bg-amber-100 text-amber-800",
  running: "bg-blue-100 text-blue-800",
  success: "bg-emerald-100 text-emerald-800",
  done: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  error: "bg-red-100 text-red-800",
  canceled: "bg-zinc-200 text-zinc-800"
};

const durationText = (started?: string | null, ended?: string | null) => {
  if (!started) return "—";
  const end = ended ? new Date(ended).getTime() : Date.now();
  const ms = end - new Date(started).getTime();
  return `${Math.max(0, Math.floor(ms / 1000))} c`;
};

export const WizardJobTimeline = memo(({ steps }: { steps: PipelineStepRun[] }) => (
  <div className="space-y-2">
    {steps.map((step) => (
      <div key={step.step_run_id} className="flex items-center justify-between rounded border p-3 text-sm">
        <div>
          <div className="font-medium">{step.step_code}</div>
          <div className="text-xs text-muted-foreground">attempt {step.attempt}</div>
          {step.error_code ? <div className="text-xs text-destructive">{step.error_code}</div> : null}
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded px-2 py-0.5 text-xs ${statusClassMap[step.status] ?? "bg-zinc-100 text-zinc-700"}`}>{step.status}</span>
          <span className="text-xs text-muted-foreground">{durationText(step.started_at, step.ended_at)}</span>
        </div>
      </div>
    ))}
  </div>
));

WizardJobTimeline.displayName = "WizardJobTimeline";
