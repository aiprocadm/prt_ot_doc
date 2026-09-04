import { useCallback, useEffect, useState } from "react";

import { tenantsApi } from "@/api/tenants";
import { formatBytes } from "@/features/tenants/FleetUsagePanel";
import type { OwnLimitLine, OwnLimitsReport } from "@/types/dto/tenants";

/**
 * Свои лимиты и свой расход (ТЗ Доп. №1 разд. 52.4, срез-15).
 *
 * Партнёр не входит в собственную область (решение среза-2: иначе он мог бы
 * приостановить сам себя), поэтому его строки нет ни в списке клиентов, ни в
 * отчёте о расходе. Свои квоты он не видел вовсе — при том что сам живёт на
 * лимитах платформы и упирается в них так же, как его клиенты.
 */

/** Величину показываем в единицах строки: байты — по-человечески, остальное
 *  числом. Иначе «использовано 5242880 из 10485760» никто не прочитает. */
export const formatAmount = (value: number, unit: string): string =>
  unit === "байт" ? formatBytes(value) : `${value} ${unit}`;

/** Что написать в строке лимита.
 *
 *  Три разных случая, и путать их нельзя: расход не считается («—»), предела
 *  нет («без ограничения»), есть и то и другое («80 из 100, осталось 20»). */
export const describeLine = (line: OwnLimitLine): string => {
  if (line.used === null) {
    return line.limit === null
      ? "не ограничено"
      : `предел ${formatAmount(line.limit, line.unit)}, расход не считается`;
  }
  const used = formatAmount(line.used, line.unit);
  if (line.limit === null) return `${used}, без ограничения`;
  const limit = formatAmount(line.limit, line.unit);
  if (line.remaining === null) return `${used} из ${limit}`;
  return `${used} из ${limit}, осталось ${formatAmount(line.remaining, line.unit)}`;
};

export const OwnLimitsPanel = () => {
  const [report, setReport] = useState<OwnLimitsReport | null>(null);

  const load = useCallback(async () => {
    try {
      setReport(await tenantsApi.ownLimits());
    } catch {
      // Клиенту эта ручка закрыта, и это не ошибка страницы: панель просто
      // не показывается. Сообщение уже показал общий перехватчик.
      setReport(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!report) return null;

  return (
    <section className="rounded-md border p-4">
      <h2 className="mb-3 text-sm font-semibold">
        Мои лимиты за {report.period}
      </h2>
      <ul className="space-y-1 text-sm">
        {report.items.map((line) => (
          <li key={line.code} className="flex flex-wrap justify-between gap-2">
            <span>{line.title}</span>
            <span
              className={
                line.exhausted
                  ? "font-medium text-destructive"
                  : "text-muted-foreground"
              }
            >
              {describeLine(line)}
              {/* Исчерпание называем словом: цвет один не читается людьми,
                  которые его не различают. */}
              {line.exhausted ? " — предел выбран" : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default OwnLimitsPanel;
