import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Collection = { total: number; items?: Array<{ id: string; dataset_code?: string; schema_version?: string; anonymized?: boolean; target_type?: string }> };

const ExportsPage = () => {
  const { t, i18n } = useTranslation();
  const [jobs, setJobs] = useState(0);
  const [schedules, setSchedules] = useState(0);
  const [kpis, setKpis] = useState(0);
  const [jobPreview, setJobPreview] = useState<Collection["items"]>([]);

  useEffect(() => {
    void apiClient.get<Collection>("/exports").then(({ data }) => {
      setJobs(Array.isArray(data) ? data.length : data.total);
      setJobPreview(Array.isArray(data) ? [] : (data.items ?? []));
    }).catch(() => undefined);
    void apiClient.get<Collection>("/exports/schedules").then(({ data }) => setSchedules(data.total)).catch(() => undefined);
    void apiClient.get<Collection>("/exports/kpis").then(({ data }) => setKpis(data.total)).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <Breadcrumb items={[{ label: t("common.home"), to: "/dashboard" }, { label: t("exports.title") }]} />
        <div className="w-full md:w-48">
          <Select value={i18n.language} onValueChange={(value) => void i18n.changeLanguage(value)}>
            <SelectTrigger aria-label={t("common.locale")}>
              <SelectValue placeholder={t("common.locale")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ru">{t("common.localeRu")}</SelectItem>
              <SelectItem value="en">{t("common.localeEn")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardHeader><CardTitle>{t("exports.jobs")}</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{jobs}</CardContent></Card>
        <Card><CardHeader><CardTitle>{t("exports.schedules")}</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{schedules}</CardContent></Card>
        <Card><CardHeader><CardTitle>{t("exports.kpis")}</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{kpis}</CardContent></Card>
      </div>
      {jobPreview?.length ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("exports.jobs")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm" aria-live="polite">
              {jobPreview.slice(0, 5).map((job) => (
                <li key={job.id} className="rounded-md border p-3">
                  <div className="font-medium">{job.dataset_code ?? job.id}</div>
                  <div className="text-muted-foreground">
                    {t("exports.schemaVersion")}: {job.schema_version ?? "v1"} · {t("exports.anonymized")}: {job.anonymized ? "yes" : "no"} · {t("exports.targetType")}: {job.target_type ?? "file"}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : (
        <EmptyState title={t("exports.jobs")} description={t("common.loading")} />
      )}
    </div>
  );
};

export default ExportsPage;
