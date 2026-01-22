import { useEffect } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RiskAssessmentForm } from "@/features/risk/RiskAssessmentForm";
import { RiskAssessmentsTable } from "@/features/risk/RiskAssessmentsTable";
import { useRiskStore } from "@/stores/risk";

const RiskPage = () => {
  const { listHazards, listAssessments, hazards } = useRiskStore();

  useEffect(() => {
    listHazards();
    listAssessments();
  }, [listAssessments, listHazards]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Риски" }]} />
      <RiskAssessmentForm />
      <Card>
        <CardHeader>
          <CardTitle className="text-xl font-semibold">Справочник опасностей</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-3 md:grid-cols-2">
            {hazards.map((hazard) => (
              <li key={hazard.id} className="rounded-md border p-3">
                <div className="font-medium">{hazard.title}</div>
                <div className="text-xs text-muted-foreground">{hazard.description}</div>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <RiskAssessmentsTable />
    </div>
  );
};

export default RiskPage;
