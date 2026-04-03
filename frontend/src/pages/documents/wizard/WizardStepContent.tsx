import { useWizardStepActions } from "./useWizardStepActions";
import type { WizardStepContentProps } from "./WizardStepContent.types";
import {
  ArchiveStep,
  BatchResultStep,
  BrandingStep,
  ExportStep,
  MappingStep,
  PresetStep,
  ReplaceStep,
  RunStep,
  SourceStep,
  TemplateStep,
} from "./steps/WizardStepSections";

export const WizardStepContent = (props: WizardStepContentProps) => {
  const actions = useWizardStepActions(props);

  if (props.step === 1) {
    return <PresetStep preset={props.preset} setPartial={props.setPartial} />;
  }
  if (props.step === 2) {
    return <SourceStep sourceColumns={props.sourceColumns} onSourceChange={actions.handleSourceFileChange} />;
  }
  if (props.step === 3) {
    return <MappingStep sourceColumns={props.sourceColumns} mapping={props.mapping} setPartial={props.setPartial} />;
  }
  if (props.step === 4) {
    return <TemplateStep templateCode={props.templateCode} templateVersion={props.templateVersion} setPartial={props.setPartial} />;
  }
  if (props.step === 5) {
    return <BrandingStep {...props} onBuildPreview={actions.handleBrandingPreview} />;
  }
  if (props.step === 6) {
    return (
      <ReplaceStep
        {...props}
        onReplaceMapChange={actions.handleReplaceMapFileChange}
        onDryRun={actions.handleReplaceDryRun}
      />
    );
  }
  if (props.step === 7) {
    return <RunStep {...props} onRunBatch={actions.handleRunBatch} onRunSinglePipeline={actions.handleRunSinglePipeline} />;
  }
  if (props.step === 8) {
    return <BatchResultStep {...props} />;
  }
  if (props.step === 9) {
    return <ExportStep pipelineRun={props.pipelineRun} onOpenArtifact={actions.handleOpenFirstArtifact} />;
  }
  return <ArchiveStep archiveStatus={props.archiveStatus} pipelineRun={props.pipelineRun} batch={props.batch} />;
};
