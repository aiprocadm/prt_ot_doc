import { useCallback } from "react";
import { toast } from "sonner";

import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DocumentRequirementFormDialog } from "@/features/contractors/DocumentRequirementFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { DOC_TYPE_LABELS, SCOPE_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ContractorDocumentRequirement } from "@/types/dto/contractors";

export const ContractorRequirementsTab = () => {
  const loader = useCallback(() => contractorsApi.listRequirements().then((p) => p.items), []);
  const { data, loading, error, reload } = useAsyncResource<ContractorDocumentRequirement[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить требования"
  });

  const onDelete = async (id: string) => {
    if (!window.confirm("Удалить требование?")) return;
    try {
      await contractorsApi.deleteRequirement(id);
      toast.success("Требование удалено");
      void reload();
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось удалить требование");
    }
  };

  if (error && isFeatureDisabledError(error)) {
    return <EmptyState title="Функция недоступна" description="Требования к документам не включены для этого тенанта." />;
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <DocumentRequirementFormDialog trigger={<Button>Новое требование</Button>} onSubmitted={() => void reload()} />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка требований" /> : null}
      {!loading && !error && data.length === 0 ? (
        <EmptyState title="Требований нет" description="Добавьте требование к документам подрядчиков." />
      ) : null}
      {!loading && !error && data.length > 0 ? (
        <ul className="divide-y rounded-md border">
          {data.map((req) => (
            <li key={req.id} className="flex items-center justify-between gap-3 p-3">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium">{DOC_TYPE_LABELS[req.doc_type] ?? req.doc_type}</span>
                <Badge variant="secondary">{SCOPE_LABELS[req.scope] ?? req.scope}</Badge>
                {req.mandatory ? <Badge>Обязательный</Badge> : <Badge variant="secondary">Необязательный</Badge>}
              </div>
              <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
                <Button variant="ghost" size="sm" onClick={() => void onDelete(req.id)}>
                  Удалить
                </Button>
              </Can>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};
