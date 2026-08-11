import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { reportsApi } from "@/api/reports";
import { EmptyState } from "@/components/common/EmptyState";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Collection = { total: number; items?: Array<{ id: string; dataset_code?: string; schema_version?: string; anonymized?: boolean; target_type?: string }> };
type DatasetCatalog = { total: number; items?: Array<{ code: string; schema_version: string; targets: string[] }> };

const ExportsPage = () => {
  const { t, i18n } = useTranslation();
  const [jobs, setJobs] = useState(0);
  const [schedules, setSchedules] = useState(0);
  const [kpis, setKpis] = useState(0);
  const [jobPreview, setJobPreview] = useState<Collection["items"]>([]);
  const [datasets, setDatasets] = useState<DatasetCatalog["items"]>([]);

  useEffect(() => {
    void reportsApi.getExports<NonNullable<Collection["items"]>[number]>().then((data) => {
      setJobs(data.total);
      setJobPreview(data.items ?? []);
    }).catch(() => undefined);
    void reportsApi.getExportSchedules().then((data) => setSchedules(data.total)).catch(() => undefined);
    void reportsApi.getExportKpis().then((data) => setKpis(data.total)).catch(() => undefined);
    void reportsApi.getDatasets<NonNullable<DatasetCatalog["items"]>[number]>().then((data) => setDatasets(data.items ?? [])).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <Breadcrumb items={[{ label: t("common.home"), to: "/dashboard" }, { label: t("exports.title") }]} />
        <div className="w-full md:w-48">
          <label className="sr-only" htmlFor="exports-language-select">
            {t("common.locale")}
          </label>
          <select
            id="exports-language-select"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
            value={i18n.language}
            onChange={(event) => void i18n.changeLanguage(event.target.value)}
          >
            <option value="ru">{t("common.localeRu")}</option>
            <option value="en">{t("common.localeEn")}</option>
          </select>
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
                    {t("exports.schemaVersion")}: {job.schema_version ?? "v1"} · {t("exports.anonymized")}: {job.anonymized ? t("common.yes") : t("common.no")} · {t("exports.targetType")}: {job.target_type ?? "file"}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : (
        <EmptyState title={t("exports.jobs")} description={t("common.loading")} />
      )}
      <Card>
        <CardHeader>
          <CardTitle>{t("exports.datasets")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm" aria-live="polite">
            {datasets?.map((dataset) => (
              <li key={dataset.code} className="rounded-md border p-3">
                <div className="font-medium">{dataset.code}</div>
                <div className="text-muted-foreground">
                  {t("exports.schemaVersion")}: {dataset.schema_version} · {t("exports.supportedTargets")}: {dataset.targets.join(", ")}
                </div>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
};

export default ExportsPage;
