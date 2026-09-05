import { useState } from "react";
import { toast } from "sonner";

import { rulesApi } from "@/api/rules";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PERMISSIONS } from "@/permissions/permissions";
import { eventLabel } from "@/pages/rules/rulesVocab";
import type { RuleLibraryPage } from "@/types/dto/rules";

/**
 * Библиотека предустановленных правил по дисциплинам (BIZ-54-57 срез-4,
 * Доп. №1 разд. 57.3).
 *
 * Показывает не только то, что есть, но и **чего нет и почему**: ноль без
 * объяснения прочитали бы как недоделку, а не как решение. С среза-62 правила
 * есть у всех восьми дисциплин — три из них живут на событии «Срок дисциплины
 * просрочен», которое даёт ежедневная проверка календаря.
 *
 * Срез-63: библиотека растёт, а посев шёл только при создании арендатора.
 * Кнопка «Выдать недостающие» даёт существующему арендатору новые правила;
 * удалённые специалистом она НЕ возвращает — и панель говорит об этом
 * числом, иначе «выдано 10 из 12» читалось бы как «два потеряли».
 *
 * Срез-66: числа мало — в строке дисциплины названы ИМЕНА: «не выдано: …»
 * (это и заведёт кнопка) и «удалено вами: …» (это она не тронет). Иначе
 * специалист гадал бы, каких двух не хватает и что именно вернёт нажатие.
 */

/** Событие, на котором живут правила по срокам дисциплин (срез-62). */
const DEADLINE_EVENT = "DisciplineDeadlineOverdue";

const rulesWord = (count: number): string => {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} правило`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14))
    return `${count} правила`;
  return `${count} правил`;
};

type Props = {
  library: RuleLibraryPage | null;
  /** Вызывается после успешной выдачи: экрану нужно перечитать и правила, и библиотеку. */
  onInstalled?: () => void;
};

export const RuleLibraryPanel = ({ library, onInstalled }: Props) => {
  const [installing, setInstalling] = useState(false);

  if (!library) return null;

  // Недостающие = ни разу не выданные. Удалённые в них не входят: их выдача
  // не вернёт, и кнопка, которая ничего не делает, хуже отсутствующей.
  const missing = library.total - library.installed - library.removed;

  const install = async () => {
    setInstalling(true);
    try {
      const result = await rulesApi.installLibrary();
      if (result.created.length > 0) {
        toast.success(`Выдано ${rulesWord(result.created.length)}`, {
          description: result.created.join("; "),
        });
      } else {
        toast.info("Новых правил в библиотеке нет");
      }
      onInstalled?.();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    } finally {
      setInstalling(false);
    }
  };

  return (
    <section data-ux-block>
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            <span>Библиотека по дисциплинам</span>
            <Badge variant="secondary">
              выдано {library.installed} из {library.total}
            </Badge>
            {library.removed > 0 ? (
              <Badge variant="outline" data-testid="rule-library-removed">
                удалено вами: {library.removed}
              </Badge>
            ) : null}
            {missing > 0 ? (
              <Can permission={PERMISSIONS.RULES_MANAGE}>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={installing}
                  onClick={() => void install()}
                >
                  Выдать недостающие ({missing})
                </Button>
              </Can>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <ul className="space-y-1 text-sm" data-testid="rule-library">
            {library.items.map((row) => (
              <li key={row.discipline} className="flex flex-wrap gap-2">
                <span className="font-medium">{row.title}:</span>
                {row.rules > 0 ? (
                  <span>{row.rules}</span>
                ) : (
                  <span className="text-muted-foreground">
                    правил нет — {row.reason}
                  </span>
                )}
                {row.missing.length > 0 ? (
                  <span
                    className="text-muted-foreground"
                    data-testid={`rule-library-missing-${row.discipline}`}
                  >
                    не выдано: {row.missing.join("; ")}
                  </span>
                ) : null}
                {row.removed.length > 0 ? (
                  <span
                    className="text-muted-foreground"
                    data-testid={`rule-library-removed-${row.discipline}`}
                  >
                    удалено вами: {row.removed.join("; ")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            Правила по срокам срабатывают на событие «
            {eventLabel(DEADLINE_EVENT)}»: его даёт ежедневная проверка общего
            календаря, одно событие на каждую просрочку.
          </p>
        </CardContent>
      </Card>
    </section>
  );
};
