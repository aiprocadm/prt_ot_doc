import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";

import { contractorsApi } from "@/api/contractors";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContractorFormDialog } from "@/features/contractors/ContractorFormDialog";
import { ContractorEmployeesTab } from "@/features/contractors/ContractorEmployeesTab";
import { ContractorDocumentsTab } from "@/features/contractors/ContractorDocumentsTab";
import { ContractorIncidentsTab } from "@/features/contractors/ContractorIncidentsTab";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { COMPLIANCE_STATUS_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ComplianceStatus, ContractorComplianceSummary, ContractorRegistry } from "@/types/dto/contractors";

type DetailData = { contractor: ContractorRegistry | null; compliance: ContractorComplianceSummary | null };

const ComplianceRow = ({ title, totals }: { title: string; totals: Record<string, number> }) => (
  <div className="rounded-md border p-3">
    <div className="mb-2 text-sm font-medium">{title}</div>
    <div className="flex flex-wrap gap-3 text-sm">
      {Object.entries(totals).length === 0 ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        Object.entries(totals).map(([status, count]) => (
          <span key={status}>
            {COMPLIANCE_STATUS_LABELS[status as ComplianceStatus] ?? status}: <strong>{count}</strong>
          </span>
        ))
      )}
    </div>
  </div>
);

export default function ContractorDetailPage() {
  const { id = "" } = useParams();

  const loader = useCallback(async (): Promise<DetailData> => {
    const [contractor, compliance] = await Promise.all([
      contractorsApi.getRegistry(id),
      contractorsApi.getComplianceSummary({ contractor_id: id })
    ]);
    return { contractor, compliance };
  }, [id]);

  const { data, loading, error, reload } = useAsyncResource<DetailData>({
    loader,
    initialData: { contractor: null, compliance: null },
    errorMessage: "Не удалось загрузить подрядчика"
  });

  if (loading) return <LoadingScreen label="Загрузка подрядчика" />;
  if (error || !data.contractor) return <ErrorState error={error ?? undefined} onRetry={() => void reload()} />;

  const c = data.contractor;

  return (
    <div className="space-y-5">
      <Link to="/contractors" className="text-sm text-muted-foreground hover:underline">
        ← Подрядчики
      </Link>

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium">{c.name}</h1>
          <p className="text-sm text-muted-foreground">
            Статус: {c.status || "—"}
            {c.inn ? ` · ИНН ${c.inn}` : ""}
            {c.contact_person ? ` · ${c.contact_person}` : ""}
            {c.contact_phone ? ` · ${c.contact_phone}` : ""}
          </p>
        </div>
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorFormDialog
            trigger={<Button variant="outline">Изменить</Button>}
            initialData={c}
            onSubmitted={() => void reload()}
          />
        </Can>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Обзор</TabsTrigger>
          <TabsTrigger value="employees">Сотрудники</TabsTrigger>
          <TabsTrigger value="documents">Документы</TabsTrigger>
          <TabsTrigger value="incidents">Инциденты</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-3">
          <p className="text-sm">Сотрудников: {data.compliance?.employees_total ?? 0}</p>
          <div className="grid gap-3 md:grid-cols-3">
            <ComplianceRow title="Допуск" totals={data.compliance?.admission ?? {}} />
            <ComplianceRow title="Обучение" totals={data.compliance?.training ?? {}} />
            <ComplianceRow title="Медосмотр" totals={data.compliance?.medical ?? {}} />
          </div>
        </TabsContent>

        <TabsContent value="employees">
          <ContractorEmployeesTab contractorId={c.id} onChanged={() => void reload()} />
        </TabsContent>

        <TabsContent value="documents">
          <ContractorDocumentsTab contractorId={c.id} />
        </TabsContent>

        <TabsContent value="incidents">
          <ContractorIncidentsTab contractorId={c.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
