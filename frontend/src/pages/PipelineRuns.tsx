import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listPipelineRuns, type PipelineRun } from "@/api/pipelines";

const PipelineRuns = () => {
  const [runs, setRuns] = useState<PipelineRun[]>([]);

  useEffect(() => {
    listPipelineRuns().then(setRuns).catch(() => setRuns([]));
  }, []);

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Пайплайны / История задач</h1>
      <div className="rounded border">
        {runs.map((run) => (
          <Link key={run.run_id} to={`/pipelines/runs/${run.run_id}`} className="flex items-center justify-between border-b p-3 text-sm hover:bg-muted/40 last:border-b-0">
            <span>{run.run_id}</span>
            <span>{run.status}</span>
          </Link>
        ))}
      </div>
    </section>
  );
};

export default PipelineRuns;
