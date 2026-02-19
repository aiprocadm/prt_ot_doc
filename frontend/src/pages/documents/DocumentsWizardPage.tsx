import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type JobStep = { name: string; status: string };
type JobRead = { id: string; status: string; steps: JobStep[] };

const DocumentsWizardPage = () => {
  const [preset, setPreset] = useState("outbound_mvp");
  const [templateCode, setTemplateCode] = useState("outbound_cover");
  const [templateVersion, setTemplateVersion] = useState("1");
  const [companyId, setCompanyId] = useState("");
  const [job, setJob] = useState<JobRead | null>(null);

  useEffect(() => {
    if (!job?.id) return;
    const timer = window.setInterval(async () => {
      const response = await apiClient.get<JobRead>(`/jobs/${job.id}`);
      setJob(response.data);
      if (response.data.status === "done" || response.data.status === "error") {
        window.clearInterval(timer);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [job?.id]);

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Wizard документов" }]} />
      <Card>
        <CardHeader>
          <CardTitle>Сквозной wizard (MVP)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input value={preset} onChange={(e) => setPreset(e.target.value)} placeholder="preset" />
          <Input value={templateCode} onChange={(e) => setTemplateCode(e.target.value)} placeholder="template code" />
          <Input value={templateVersion} onChange={(e) => setTemplateVersion(e.target.value)} placeholder="template version" />
          <Input value={companyId} onChange={(e) => setCompanyId(e.target.value)} placeholder="company id" />
          <Button
            onClick={async () => {
              const response = await apiClient.post<{ task_id: string }>("/documents/generate", {
                template_code: templateCode,
                template_version: Number(templateVersion),
                company_id: companyId,
                data: { preset }
              });
              const status = await apiClient.get<JobRead>(`/jobs/${response.data.task_id}`);
              setJob(status.data);
            }}
          >
            Run pipeline
          </Button>
        </CardContent>
      </Card>
      {job ? (
        <Card>
          <CardHeader>
            <CardTitle>Timeline: {job.status}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {job.steps.map((step) => (
                <li key={step.name}>
                  {step.name}: <b>{step.status}</b>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};

export default DocumentsWizardPage;
