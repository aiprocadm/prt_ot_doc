import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import {
  acceptLegalDocument,
  getLegalAcceptanceState,
  type LegalAcceptanceStatus,
  type LegalDocumentKind,
} from "@/api/legalDocuments";
import { Button } from "@/components/ui/button";

/**
 * Напоминание принять юридические тексты (ТЗ Доп. №1 разд. 52.2, срез-11).
 *
 * Сервер умеет записывать принятие, но человек об этом не узнает, если ему не
 * сказать: страницу оферты по своей воле не открывают. Полоса появляется только
 * когда подпись действительно нужна, и исчезает сразу после неё.
 */

const KIND_LABELS: Record<LegalDocumentKind, string> = {
  offer: "оферту",
  privacy: "политику обработки персональных данных",
  consent: "согласие на обработку персональных данных",
};

export const LegalAcceptanceBanner = () => {
  const [pending, setPending] = useState<LegalAcceptanceStatus[]>([]);
  const [busy, setBusy] = useState<LegalDocumentKind | null>(null);

  const load = useCallback(async () => {
    try {
      const state = await getLegalAcceptanceState();
      // Признак «надо подписать» считает СЕРВЕР: вычислять его здесь значит
      // завести вторую правду о том, принят документ или нет.
      const kinds = new Set(state.pending);
      setPending(state.items.filter((item) => kinds.has(item.kind)));
    } catch {
      // Молча: неудачный запрос не повод пугать человека полосой «примите
      // оферту», которой может и не быть. Ошибку уже показал перехватчик.
      setPending([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accept = async (kind: LegalDocumentKind) => {
    setBusy(kind);
    try {
      await acceptLegalDocument(kind);
      toast.success("Принято");
      await load();
    } catch {
      /* сообщение уже показал общий перехватчик запросов */
    } finally {
      setBusy(null);
    }
  };

  if (pending.length === 0) return null;

  return (
    <div className="mb-4 space-y-2 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950">
      {pending.map((item) => (
        <div
          key={item.kind}
          className="flex flex-wrap items-center justify-between gap-2"
        >
          <span>
            {/* «Условия изменились» и «примите оферту» — разные сообщения:
                человека, уже подписавшего прежнюю редакцию, второе сбивало бы
                с толку. */}
            {item.outdated
              ? `Условия изменились: перечитайте ${KIND_LABELS[item.kind]}.`
              : `Примите ${KIND_LABELS[item.kind]}, чтобы продолжить работу.`}{" "}
            <Link
              className="underline"
              to={`/legal/${item.kind}`}
              target="_blank"
            >
              Прочитать
            </Link>
          </span>
          <Button
            size="sm"
            disabled={busy === item.kind}
            onClick={() => void accept(item.kind)}
          >
            {busy === item.kind ? "Сохранение..." : "Принимаю"}
          </Button>
        </div>
      ))}
    </div>
  );
};

export default LegalAcceptanceBanner;
