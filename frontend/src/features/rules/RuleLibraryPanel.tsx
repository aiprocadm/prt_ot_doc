import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RuleLibraryPage } from "@/types/dto/rules";

/**
 * Библиотека предустановленных правил по дисциплинам (BIZ-54-57 срез-4,
 * Доп. №1 разд. 57.3).
 *
 * Показывает не только то, что есть, но и **чего нет и почему**. У экологии,
 * ГО-ЧС и БДД в продукте нет ни одного события, и правило пришлось бы вешать
 * на свободный текст — то есть на угадайку. Ноль без объяснения прочитали бы
 * как недоделку, а не как решение.
 */

type Props = {
  library: RuleLibraryPage | null;
};

export const RuleLibraryPanel = ({ library }: Props) => {
  if (!library) return null;

  return (
    <section data-ux-block>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Библиотека по дисциплинам
            <Badge className="ml-2" variant="secondary">
              выдано {library.installed} из {library.total}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
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
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
};
