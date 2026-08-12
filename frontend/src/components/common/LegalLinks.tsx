import { useEffect, useState } from "react";

import {
  listLegalDocuments,
  type LegalDocumentSummary,
} from "@/api/legalDocuments";

/**
 * Ссылки на юридические тексты арендатора (ТЗ Доп. №1 разд. 52.2).
 *
 * Показываются на экране входа: человек обязан иметь возможность прочитать
 * оферту и политику ПДн ДО того, как войдёт. Тексты берутся публичной ручкой —
 * токена на этом экране ещё нет.
 *
 * **Ничего не опубликовано — не показываем ничего.** Пустой заголовок «Документы»
 * без ссылок выглядит как поломка загрузки; отсутствие блока читается верно.
 */
export const LegalLinks = () => {
  const [items, setItems] = useState<LegalDocumentSummary[]>([]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const documents = await listLegalDocuments();
        if (mounted) setItems(documents);
      } catch {
        // Молча: отсутствие юр. текстов не должно мешать входу в систему.
        if (mounted) setItems([]);
      }
    };
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  if (items.length === 0) return null;

  return (
    <nav
      aria-label="Юридические документы"
      className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"
    >
      {items.map((item) => (
        <a
          key={item.kind}
          className="underline underline-offset-2 hover:text-foreground"
          href={`/legal/${item.kind}`}
        >
          {item.title}
        </a>
      ))}
    </nav>
  );
};
