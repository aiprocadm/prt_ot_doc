import { useEffect, useRef, useState } from "react";

import { importsApi } from "@/api/imports";
import type { ImportBatchDto } from "@/types/dto/imports";

/** Статусы, из которых партия уже не сдвинется — опрашивать их бессмысленно. */
const TERMINAL = new Set(["applied", "failed", "rolled_back"]);

export const POLL_INTERVAL_MS = 2000;

/**
 * Живой статус фоновых партий (OPS-71 разд. 71.1, строка «Прогресс»).
 *
 * Опрашиваются ТОЛЬКО незавершённые партии, и опрос сам останавливается, когда
 * таких не остаётся: бесконечный таймер на странице, где всё давно загрузилось,
 * — это фоновый трафик, который никто не замечает, пока он не станет проблемой.
 *
 * Ответ сервера кладётся поверх списка со страницы, а не заменяет его: список
 * перезагружается по своим причинам, и терять свежий прогресс при каждом
 * reload() нельзя.
 */
export const useBatchProgress = (
  batches: ImportBatchDto[],
  options: { onSettled?: () => void; intervalMs?: number } = {},
): ImportBatchDto[] => {
  const { onSettled, intervalMs = POLL_INTERVAL_MS } = options;
  const [live, setLive] = useState<Record<string, ImportBatchDto>>({});
  // Колбэк в ref: иначе новая функция на каждый рендер родителя перезапускала бы
  // таймер, и опрос сбрасывался бы, ни разу не дойдя до срабатывания.
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  const merged = batches.map((batch) => live[batch.id] ?? batch);
  const activeIds = merged
    .filter((batch) => !TERMINAL.has(batch.status))
    .map((batch) => batch.id);
  // Ключ по составу активных партий: пока он не меняется, эффект не перезапускается.
  const activeKey = activeIds.join(",");

  useEffect(() => {
    if (!activeKey) return undefined;
    let cancelled = false;

    const tick = async () => {
      const ids = activeKey.split(",");
      const results = await Promise.all(
        ids.map((id) => importsApi.batch(id).catch(() => null)),
      );
      if (cancelled) return;

      const fresh: Record<string, ImportBatchDto> = {};
      let settled = false;
      for (const batch of results) {
        if (!batch) continue;
        fresh[batch.id] = batch;
        if (TERMINAL.has(batch.status)) settled = true;
      }
      if (Object.keys(fresh).length > 0) {
        setLive((prev) => ({ ...prev, ...fresh }));
      }
      // Партия завершилась — списку пора обновиться целиком: в терминальном
      // состоянии появляются счётчики и отчёт, которых в прогрессе не было.
      if (settled) onSettledRef.current?.();
    };

    const timer = setInterval(() => void tick(), intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [activeKey, intervalMs]);

  return merged;
};
