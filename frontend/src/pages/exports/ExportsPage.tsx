import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiClient } from "@/api/client";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Collection = { total: number };

const ExportsPage = () => {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState(0);
  const [schedules, setSchedules] = useState(0);
  const [kpis, setKpis] = useState(0);

  useEffect(() => {
    void apiClient.get<Collection>("/exports").then(({ data }) => setJobs(Array.isArray(data) ? data.length : data.total)).catch(() => undefined);
    void apiClient.get<Collection>("/exports/schedules").then(({ data }) => setSchedules(data.total)).catch(() => undefined);
    void apiClient.get<Collection>("/exports/kpis").then(({ data }) => setKpis(data.total)).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: t("exports.title") }]} />
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardHeader><CardTitle>{t("exports.jobs")}</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{jobs}</CardContent></Card>
        <Card><CardHeader><CardTitle>{t("exports.schedules")}</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{schedules}</CardContent></Card>
        <Card><CardHeader><CardTitle>{t("exports.kpis")}</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{kpis}</CardContent></Card>
      </div>
    </div>
  );
};

export default ExportsPage;
