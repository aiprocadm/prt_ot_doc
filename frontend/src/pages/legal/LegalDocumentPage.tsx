import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import {
  getLegalDocument,
  type LegalDocument,
  type LegalDocumentKind,
} from "@/api/legalDocuments";

const KNOWN_KINDS: LegalDocumentKind[] = ["offer", "privacy", "consent"];

/**
 * Чтение юридического текста (ТЗ Доп. №1 разд. 52.2).
 *
 * Страница ПУБЛИЧНАЯ — вне защищённого дерева: оферту и политику ПДн человек
 * обязан прочитать до входа. Требуй здесь авторизацию — и ссылка с экрана входа
 * вела бы обратно на экран входа.
 */
export const LegalDocumentPage = () => {
  const { kind } = useParams<{ kind: string }>();
  const [document, setDocument] = useState<LegalDocument | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing">(
    "loading",
  );

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      if (!kind || !KNOWN_KINDS.includes(kind as LegalDocumentKind)) {
        if (mounted) setState("missing");
        return;
      }
      try {
        const loaded = await getLegalDocument(kind as LegalDocumentKind);
        if (!mounted) return;
        setDocument(loaded);
        setState("ready");
      } catch {
        if (mounted) setState("missing");
      }
    };
    void load();
    return () => {
      mounted = false;
    };
  }, [kind]);

  if (state === "loading") {
    return <div className="p-6 text-sm text-muted-foreground">Загрузка…</div>;
  }

  if (state === "missing" || !document) {
    return (
      <div className="mx-auto max-w-3xl space-y-2 p-6">
        <h1 className="text-xl font-bold">Документ не опубликован</h1>
        <p className="text-sm text-muted-foreground">
          Обслуживающая компания пока не разместила этот документ.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold">{document.title}</h1>
        {/* Редакция и дата обязательны: юридический текст без них не отвечает
            на вопрос «что действовало на такую-то дату». */}
        <p className="text-xs text-muted-foreground">
          Редакция {document.version} от{" "}
          {new Date(document.published_at).toLocaleDateString("ru-RU")}
        </p>
      </div>
      <article className="whitespace-pre-wrap text-sm leading-relaxed">
        {document.body}
      </article>
    </div>
  );
};

export default LegalDocumentPage;
