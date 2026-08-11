import { useEffect } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RiskAssessmentForm } from "@/features/risk/RiskAssessmentForm";
import { RiskAssessmentsTable } from "@/features/risk/RiskAssessmentsTable";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { useRiskStore } from "@/stores/risk";

const RiskPage = () => {
  const { listHazards, listAssessments, hazards, assessments, loading, error } =
    useRiskStore();
  const { can } = useAbility();
  const canView = can(PERMISSIONS.RISK_VIEW);

  useEffect(() => {
    if (canView) {
      listHazards();
      listAssessments();
    }
  }, [canView, listAssessments, listHazards]);

  if (!canView) {
    return <AccessDeniedPage />;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[{ label: "Главная", to: "/dashboard" }, { label: "Риски" }]}
      />
      <ErrorState
        error={error ?? undefined}
        onRetry={() => {
          void listHazards();
          void listAssessments();
        }}
      />
      {loading && hazards.length === 0 && assessments.length === 0 ? (
        <LoadingScreen label="Загрузка реестра рисков" />
      ) : null}
      <RiskAssessmentForm />
      <Card>
        <CardHeader>
          <CardTitle className="text-xl font-semibold">
            Справочник опасностей
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!loading && !error && hazards.length === 0 ? (
            <EmptyState
              title="Опасности пока не заведены"
              description="Добавьте опасности в тенант, чтобы начать полноценную оценку рисков и не работать вслепую."
            />
          ) : null}
          {hazards.length > 0 ? (
            <ul className="grid gap-3 md:grid-cols-2">
              {hazards.map((hazard) => (
                <li key={hazard.id} className="rounded-md border p-3">
                  <div className="font-medium">{hazard.title}</div>
                  <div className="text-xs text-muted-foreground">
                    {hazard.description}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>
      <RiskAssessmentsTable />
    </div>
  );
};

export default RiskPage;
