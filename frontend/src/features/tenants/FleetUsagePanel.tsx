import { useCallback, useEffect, useState } from "react";

import { tenantsApi } from "@/api/tenants";
import type { FleetUsageReport } from "@/types/dto/tenants";

/**
 * Расход клиентов за месяц (ТЗ Доп. №1 разд. 52.4, срез-13).
 *
 * Ручка `GET /platform/tenants/usage` существует с среза-8, но кабинет её не
 * вызывал: партнёр не видел расход вовсе и не мог выставить клиенту счёт, не
 * заглянув в базу. Панель закрывает этот разрыв и заодно показывает метрики,
 * добавленные этим срезом — хранилище и активных сотрудников.
 */

/** Байты человеку. Гигабайты у клиента-крупняка и килобайты у новичка должны
 *  читаться одинаково легко, поэтому единица выбирается по величине. */
export const formatBytes = (value: number): string => {
  if (!Number.isFinite(value) || value <= 0) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  const power = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const scaled = value / 1024 ** power;
  // Целые байты не дробим, и круглые значения показываем без хвостового нуля:
  // «1536,0 Б» и «2,0 КБ» читаются как огрех расчёта.
  const digits = power === 0 || scaled >= 100 ? 0 : 1;
  const text = scaled.toFixed(digits).replace(/[.,]0$/, "").replace(".", ",");
  return `${text} ${units[power]}`;
};

export const FleetUsagePanel = () => {
  const [report, setReport] = useState<FleetUsageReport | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setReport(await tenantsApi.usage());
      setFailed(false);
    } catch {
      // Расход — не главное на странице клиентов: неудачный запрос не должен
      // мешать заводить и вести клиентов. Ошибку уже показал перехватчик.
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (failed || !report) return null;

  return (
    <section className="rounded-md border p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Расход за {report.period}</h2>
        <span className="text-xs text-muted-foreground">
          Документов: {report.total_doc_generations} · Хранилище:{" "}
          {formatBytes(report.total_storage_bytes)} · Сотрудников:{" "}
          {report.total_active_workers}
        </span>
      </div>

      {report.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          За этот месяц расхода не было.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Расход клиентов за месяц</caption>
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1 pr-4 font-normal">Клиент</th>
                <th className="py-1 pr-4 font-normal">Документы</th>
                <th className="py-1 pr-4 font-normal">Хранилище</th>
                <th className="py-1 font-normal">Сотрудники</th>
              </tr>
            </thead>
            <tbody>
              {report.items.map((row) => (
                <tr key={row.tenant_id} className="border-t">
                  <td className="py-1 pr-4">{row.name}</td>
                  <td className="py-1 pr-4">{row.doc_generations}</td>
                  <td className="py-1 pr-4">{formatBytes(row.storage_bytes)}</td>
                  <td className="py-1">{row.active_workers}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {report.not_measured.length > 0 ? (
        // Молчание о неучитываемом читалось бы как «этим не пользуются».
        <p className="mt-3 text-xs text-muted-foreground">
          Не учитывается: {report.not_measured.join("; ")}.
        </p>
      ) : null}
    </section>
  );
};

export default FleetUsagePanel;
