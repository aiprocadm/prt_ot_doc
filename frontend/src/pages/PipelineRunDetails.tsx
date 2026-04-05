import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { cancelPipelineRun, getPipelineRun, retryPipelineRun, retryPipelineStepRun, type PipelineRun } from "@/api/pipelines";
import { getFile, listEntityFiles, reindexFile } from "@/api/files";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { JobTimeline } from "@/components/JobTimeline";
import { FileList } from "@/features/files/FileList";
import type { ApiError } from "@/types/dto/common";

const PipelineRunDetails = () => {
  const { id = "" } = useParams();
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [indexStatus, setIndexStatus] = useState<string>("—");
  const [indexedFileId, setIndexedFileId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const nextRun = await getPipelineRun(id);
      setRun(nextRun);
    } catch (loadError) {
      setRun(null);
      setError(loadError as ApiError);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [id]);

  const sseRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!id) return;
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }

    let pollTimer: number | null = null;
    const startPolling = () => {
      if (pollTimer) return;
      pollTimer = window.setInterval(() => {
        getPipelineRun(id)
          .then((nextRun) => {
            setRun(nextRun);
            setError(null);
          })
          .catch(() => undefined);
      }, 3000);
    };

    try {
      const source = new EventSource(`/api/v1/pipelines/runs/${id}/events`, { withCredentials: true });
      sseRef.current = source;
      source.addEventListener("run.update", (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent<string>).data) as PipelineRun;
          setRun(payload);
          setError(null);
        } catch {
          getPipelineRun(id)
            .then((nextRun) => {
              setRun(nextRun);
              setError(null);
            })
            .catch(() => undefined);
        }
      });
      source.addEventListener("run.done", (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent<string>).data) as PipelineRun;
          setRun(payload);
          setError(null);
        } finally {
          source.close();
          sseRef.current = null;
        }
      });
      source.onerror = () => {
        source.close();
        sseRef.current = null;
        startPolling();
      };
    } catch {
      startPolling();
    }

    return () => {
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
      if (pollTimer) window.clearInterval(pollTimer);
    };
  }, [id]);

  const failedStep = useMemo(() => run?.step_runs.find((s) => s.status === "failed"), [run]);

  const stepLogs = useMemo(() => run?.logs ?? [], [run]);

  useEffect(() => {
    if (!run?.run_id) return;
    listEntityFiles("job", run.run_id)
      .then(async (files) => {
        const candidate = files[0]?.file_id;
        if (!candidate) {
          setIndexedFileId(null);
          setIndexStatus("—");
          return;
        }
        setIndexedFileId(candidate);
        const file = await getFile(candidate);
        setIndexStatus(file.content_index?.status ?? "queued");
      })
      .catch(() => {
        setIndexedFileId(null);
        setIndexStatus("—");
      });
  }, [run?.run_id]);
  if (loading) {
    return <LoadingScreen label="Загрузка запуска пайплайна" />;
  }

  if (error) {
    return <ErrorState error={error} onRetry={() => void load()} />;
  }

  if (!run) {
    return (
      <section className="space-y-4">
        <EmptyState
          title="Запуск пайплайна не найден"
          description="Проверьте идентификатор запуска или обновите страницу после повторного запуска задачи."
        />
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Задание {run.run_id}</h1>
      <div className="flex gap-2">
        <button
          className="rounded border px-3 py-1"
          onClick={() =>
            retryPipelineRun(run.run_id)
              .then((nextRun) => {
                setRun(nextRun);
                setError(null);
              })
              .catch((actionError) => setError(actionError as ApiError))
          }
        >
          Retry failed
        </button>
        {failedStep ? (
          <button
            className="rounded border px-3 py-1"
            onClick={() =>
              retryPipelineStepRun(run.run_id, failedStep.step_run_id)
                .then((nextRun) => {
                  setRun(nextRun);
                  setError(null);
                })
                .catch((actionError) => setError(actionError as ApiError))
            }
          >
            Повторить шаг
          </button>
        ) : null}
        <button
          className="rounded border px-3 py-1"
          onClick={() =>
            cancelPipelineRun(run.run_id)
              .then((nextRun) => {
                setRun(nextRun);
                setError(null);
              })
              .catch((actionError) => setError(actionError as ApiError))
          }
        >
          Отменить
        </button>
      </div>
      <JobTimeline steps={run.step_runs} />
      <div className="rounded border p-3 text-sm">
        <h2 className="mb-2 font-medium">Найдено по содержимому</h2>
        <p className="text-muted-foreground">Файлы проиндексированы: <span className="font-medium">{indexStatus}</span></p>
        <button
          className="mt-2 rounded border px-3 py-1"
          disabled={!indexedFileId}
          onClick={async () => {
            if (!indexedFileId) return;
            await reindexFile(indexedFileId);
            setIndexStatus("queued");
          }}
        >
          Переиндексировать
        </button>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded border p-3 text-sm">
          <h2 className="mb-2 font-medium">Логи шагов</h2>
          <div className="max-h-56 space-y-1 overflow-auto">
            {stepLogs.length === 0 ? (
              <EmptyState
                title="Логи пока отсутствуют"
                description="События шагов появятся здесь после старта обработки или при поступлении обновлений."
              />
            ) : (
              stepLogs.slice(-50).map((log, idx) => (
                <div key={`${log.timestamp}-${idx}`} className="text-xs">
                  <span className="text-muted-foreground">[{log.level}]</span> {log.step_name ? `${log.step_name}: ` : ""}{log.message}
                </div>
              ))
            )}
          </div>
        </div>
        <div className="rounded border p-3 text-sm">
          <h2 className="mb-2 font-medium">Артефакты</h2>
          <FileList entityType="job" entityId={run.run_id} />
        </div>
      </div>
    </section>
  );
};

export default PipelineRunDetails;
