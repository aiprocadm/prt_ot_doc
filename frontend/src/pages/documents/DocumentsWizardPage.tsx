import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { useDocumentsWizardStore } from "@/stores/documentsWizard";

import { wizardSteps } from "./wizard/constants";
import { WizardStepContent } from "./wizard/WizardStepContent";
import { useDocumentsWizardBootstrap } from "./wizard/useDocumentsWizardBootstrap";
import { getArchiveStatusSummary } from "./wizard/utils";
import { WizardStepper } from "@/components/wizard/WizardStepper";

const DocumentsWizardPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryStep = searchParams.get("step");
  const {
    tenant,
    companies,
    sites,
    layoutPresets,
    brandingProfileScope
  } = useDocumentsWizardBootstrap();

  const {
    step,
    preset,
    sourceColumns,
    mapping,
    templateCode,
    templateVersion,
    companyId,
    siteId,
    headerPreset,
    replaceDryRun: replaceDryRunResult,
    batch,
    pipelineRun,
    brandingPreview,
    brandingPreviewHistory,
    idempotencyKey,
    rowStatusFilter,
    pushBrandingPreview,
    setPartial
  } = useDocumentsWizardStore();

  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [replaceMapFile, setReplaceMapFile] = useState<File | null>(null);
  const [docxFile, setDocxFile] = useState<File | null>(null);
  const [batchErrors, setBatchErrors] = useState("");

  useEffect(() => {
    const stepFromQuery = Number(queryStep ?? step);
    if (Number.isFinite(stepFromQuery) && stepFromQuery >= 1 && stepFromQuery <= 10 && stepFromQuery !== step) {
      setPartial({ step: stepFromQuery });
    }
  }, [queryStep, setPartial, step]);

  useEffect(() => {
    if (queryStep !== String(step)) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("step", String(step));
        return next;
      }, { replace: true });
    }
  }, [queryStep, setSearchParams, step]);

  const filteredBatchItems = useMemo(() => {
    if (!batch) return [];
    if (rowStatusFilter === "all") return batch.items;
    return batch.items.filter((item) => item.status === rowStatusFilter);
  }, [batch, rowStatusFilter]);

  useUnsavedChanges(Boolean(sourceFile || replaceMapFile || docxFile));

  const archiveStatus = getArchiveStatusSummary({
    batchStatus: batch?.status,
    pipelineStatus: pipelineRun?.status
  });

  const canCallApi = Boolean(tenant);

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Документы" }, { label: "Мастер пакета" }]} />
      {!tenant ? (
        <Card><CardContent className="pt-6 text-sm text-destructive">Выберите tenant перед запуском мастера. Без X-Tenant запросы заблокированы.</CardContent></Card>
      ) : null}
      <WizardStepper steps={wizardSteps.map((item) => ({ ...item }))} currentStep={step} onStepClick={(s) => setPartial({ step: s })} />

      <Card>
        <CardHeader><CardTitle>Шаг {step}: {wizardSteps[step - 1].title}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <WizardStepContent
            step={step}
            canCallApi={canCallApi}
            sourceColumns={sourceColumns}
            mapping={mapping}
            preset={preset}
            templateCode={templateCode}
            templateVersion={templateVersion}
            companyId={companyId}
            siteId={siteId}
            headerPreset={headerPreset}
            idempotencyKey={idempotencyKey}
            rowStatusFilter={rowStatusFilter}
            filteredBatchItems={filteredBatchItems}
            replaceDryRunResult={replaceDryRunResult}
            batch={batch}
            pipelineRun={pipelineRun}
            brandingPreview={brandingPreview}
            brandingPreviewHistory={brandingPreviewHistory}
            brandingProfileScope={brandingProfileScope}
            companies={companies}
            sites={sites}
            layoutPresets={layoutPresets}
            sourceFile={sourceFile}
            replaceMapFile={replaceMapFile}
            docxFile={docxFile}
            batchErrors={batchErrors}
            setSourceFile={setSourceFile}
            setReplaceMapFile={setReplaceMapFile}
            setDocxFile={setDocxFile}
            setBatchErrors={setBatchErrors}
            pushBrandingPreview={pushBrandingPreview}
            setPartial={setPartial}
            archiveStatus={archiveStatus}
          />

          <div className="flex justify-between border-t pt-3">
            <Button variant="outline" onClick={() => setPartial({ step: Math.max(step - 1, 1) })} disabled={step === 1}>Назад</Button>
            <Button onClick={() => setPartial({ step: Math.min(step + 1, 10) })} disabled={step === 10}>Далее</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default DocumentsWizardPage;
