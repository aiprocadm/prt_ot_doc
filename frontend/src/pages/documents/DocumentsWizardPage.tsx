import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

const clampStep = (value: number) =>
  Math.min(Math.max(value, 1), wizardSteps.length);

const DocumentsWizardPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryStep = searchParams.get("step");
  const didInitFromQueryRef = useRef(false);
  const { tenant, companies, sites, layoutPresets, brandingProfileScope } =
    useDocumentsWizardBootstrap();

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
    mappingValidation,
    qualityReport,
    batch,
    pipelineRun,
    brandingPreview,
    brandingPreviewHistory,
    idempotencyKey,
    rowStatusFilter,
    pushBrandingPreview,
    setPartial,
  } = useDocumentsWizardStore();
  const normalizedStep = clampStep(step);

  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [replaceMapFile, setReplaceMapFile] = useState<File | null>(null);
  const [docxFile, setDocxFile] = useState<File | null>(null);
  const [batchErrors, setBatchErrors] = useState("");

  useEffect(() => {
    if (step !== normalizedStep) {
      setPartial({ step: normalizedStep });
    }
  }, [normalizedStep, setPartial, step]);

  useEffect(() => {
    if (didInitFromQueryRef.current) return;
    didInitFromQueryRef.current = true;
    if (queryStep === null) return;
    const stepFromQuery = Number(queryStep ?? "");
    if (!Number.isFinite(stepFromQuery)) return;
    const clamped = clampStep(stepFromQuery);
    if (clamped !== normalizedStep) {
      setPartial({ step: clamped });
    }
  }, [normalizedStep, queryStep, setPartial]);

  useEffect(() => {
    if (queryStep !== String(normalizedStep)) {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("step", String(normalizedStep));
          return next;
        },
        { replace: true },
      );
    }
  }, [normalizedStep, queryStep, setSearchParams]);

  const filteredBatchItems = useMemo(() => {
    if (!batch) return [];
    if (rowStatusFilter === "all") return batch.items;
    return batch.items.filter((item) => item.status === rowStatusFilter);
  }, [batch, rowStatusFilter]);

  useUnsavedChanges(Boolean(sourceFile || replaceMapFile || docxFile));

  const archiveStatus = useMemo(
    () =>
      getArchiveStatusSummary({
        batchStatus: batch?.status,
        pipelineStatus: pipelineRun?.status,
      }),
    [batch?.status, pipelineRun?.status],
  );

  const handleStepClick = useCallback(
    (s: number) => {
      const nextStep = clampStep(s);
      if (nextStep !== normalizedStep) {
        setPartial({ step: nextStep });
      }
    },
    [normalizedStep, setPartial],
  );

  const goPrevStep = useCallback(() => {
    setPartial({ step: clampStep(normalizedStep - 1) });
  }, [normalizedStep, setPartial]);

  const goNextStep = useCallback(() => {
    setPartial({ step: clampStep(normalizedStep + 1) });
  }, [normalizedStep, setPartial]);

  const canCallApi = Boolean(tenant);

  return (
    <div className="space-y-4">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Документы" },
          { label: "Мастер пакета" },
        ]}
      />
      {!tenant ? (
        <Card>
          <CardContent className="pt-6 text-sm text-destructive">
            Выберите tenant перед запуском мастера. Без X-Tenant запросы
            заблокированы.
          </CardContent>
        </Card>
      ) : null}
      <WizardStepper
        steps={wizardSteps}
        currentStep={normalizedStep}
        onStepClick={handleStepClick}
      />

      <Card>
        <CardHeader>
          <CardTitle>
            Шаг {normalizedStep}: {wizardSteps[normalizedStep - 1].title}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <WizardStepContent
            step={normalizedStep}
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
            mappingValidation={mappingValidation}
            qualityReport={qualityReport}
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
            <Button
              variant="outline"
              onClick={goPrevStep}
              disabled={normalizedStep === 1}
            >
              Назад
            </Button>
            <Button
              onClick={goNextStep}
              disabled={normalizedStep === wizardSteps.length}
            >
              Далее
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default DocumentsWizardPage;
