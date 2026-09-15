import { useState } from "react";
import { toast } from "sonner";

import { npaApi } from "@/api/npa";
import { Button } from "@/components/ui/button";
import type { NpaRevisionDiffDto } from "@/types/dto/npa";

/**
 * Сравнение двух редакций акта (срез-202, B.18 разд. 19.4).
 *
 * ГЛАВНОЕ НА ВИТРИНЕ — «сравнивать нечем» показывается ПРИЧИНОЙ, а не пустым
 * списком. У редакций, заведённых до среза-202, текста нет вовсе; пустой
 * список изменений человек прочитал бы как «закон не менялся» и не стал бы
 * пересматривать документы. Ровно тот класс вранья, который срез-197 вылавливал
 * у сводки влияния, где отсутствие строки читалось как «вас не задевает».
 *
 * Выбор редакций не подставляется за человека в обратную сторону: «что стало
 * при переходе от A к B» и «от B к A» — разные вопросы, добавленный пункт в
 * обратную сторону становится исключённым.
 */

export interface CompareRevisionOption {
  id: string;
  revision_code: string;
  has_text?: boolean;
}

interface NpaRevisionCompareProps {
  actId: string;
  revisions: CompareRevisionOption[];
}

const TONE: Record<string, string> = {
  added: "border-l-4 border-emerald-500 bg-emerald-50",
  removed: "border-l-4 border-rose-500 bg-rose-50",
  modified: "border-l-4 border-amber-500 bg-amber-50",
};

export const NpaRevisionCompare = ({
  actId,
  revisions,
}: NpaRevisionCompareProps) => {
  const [base, setBase] = useState("");
  const [target, setTarget] = useState("");
  const [diff, setDiff] = useState<NpaRevisionDiffDto | null>(null);
  const [loading, setLoading] = useState(false);

  // Сравнивать есть что только начиная с двух редакций: с одной вопрос
  // «что изменилось» не имеет смысла, и предлагать его — обещать впустую.
  if (revisions.length < 2) return null;

  const compare = async () => {
    if (!base || !target || base === target) return;
    setLoading(true);
    try {
      setDiff(await npaApi.compareRevisions(actId, base, target));
    } catch {
      toast.error("Не удалось сравнить редакции");
      setDiff(null);
    } finally {
      setLoading(false);
    }
  };

  const label = (option: CompareRevisionOption) =>
    option.has_text
      ? option.revision_code
      : `${option.revision_code} — текста нет`;

  return (
    // Блок свёрнут по умолчанию — и это не только про UX-бюджет (разд. 59.2,
    // два выбора вывели бы карточку акта за лимит видимых полей). Сравнение
    // редакций — действие ПО ЗАПРОСУ: человек открывает карточку, чтобы увидеть
    // зависимости и сроки, а «что изменилось» спрашивает отдельно и не всегда.
    <details
      className="mt-3 rounded border p-3"
      data-testid="npa-revision-compare"
    >
      <summary className="cursor-pointer text-xs font-medium uppercase text-muted-foreground">
        Что изменилось между редакциями
      </summary>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <label className="text-xs" htmlFor="npa-diff-base">
            От редакции
          </label>
          <select
            id="npa-diff-base"
            className="block h-9 rounded border px-2 text-sm"
            value={base}
            onChange={(event) => setBase(event.target.value)}
          >
            <option value="">—</option>
            {revisions.map((revision) => (
              <option key={revision.id} value={revision.id}>
                {label(revision)}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs" htmlFor="npa-diff-target">
            К редакции
          </label>
          <select
            id="npa-diff-target"
            className="block h-9 rounded border px-2 text-sm"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
          >
            <option value="">—</option>
            {revisions.map((revision) => (
              <option key={revision.id} value={revision.id}>
                {label(revision)}
              </option>
            ))}
          </select>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={!base || !target || base === target || loading}
          onClick={() => void compare()}
        >
          {loading ? "Сравнение..." : "Сравнить"}
        </Button>
      </div>

      {diff && !diff.comparable ? (
        // Причина, а не пустой список: «текста нет» и «изменений нет» — разные
        // ответы, и человек должен видеть, какой из них перед ним.
        <p
          className="mt-3 rounded bg-muted p-2 text-sm text-muted-foreground"
          data-testid="npa-diff-unavailable"
        >
          {diff.reason}
        </p>
      ) : null}

      {diff?.comparable ? (
        <div className="mt-3 space-y-2" data-testid="npa-diff-result">
          <div className="text-sm text-muted-foreground">
            Добавлено: {diff.summary.added} · Исключено: {diff.summary.removed}{" "}
            · Изменено: {diff.summary.modified} · Без изменений:{" "}
            {diff.summary.unchanged}
          </div>
          {diff.changes.length === 0 ? (
            <p className="text-sm">
              Текст редакций совпадает — пункты не менялись.
            </p>
          ) : (
            diff.changes.map((change) => (
              <div
                key={change.code}
                className={`rounded p-2 text-sm ${TONE[change.change] ?? ""}`}
                data-testid="npa-diff-change"
                data-change={change.change}
              >
                <div className="font-medium">
                  {change.code} · {change.change_title}
                </div>
                {change.before ? (
                  <div className="mt-1 text-muted-foreground line-through">
                    {change.before}
                  </div>
                ) : null}
                {change.after ? (
                  <div className="mt-1">{change.after}</div>
                ) : null}
              </div>
            ))
          )}
        </div>
      ) : null}
    </details>
  );
};
