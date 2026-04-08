import { memo } from "react";

import { cn } from "@/utils/cn";

export type WizardStep = {
  id: number;
  title: string;
  description: string;
};

export const WizardStepper = memo(({
  steps,
  currentStep,
  onStepClick
}: {
  steps: readonly WizardStep[];
  currentStep: number;
  onStepClick: (step: number) => void;
}) => (
  <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
    {steps.map((step) => {
      const isCurrent = step.id === currentStep;
      const isDone = step.id < currentStep;
      return (
        <button
          key={step.id}
          type="button"
          className={cn(
            "rounded border p-3 text-left transition",
            isCurrent && "border-primary bg-primary/5",
            isDone && "border-emerald-500/40 bg-emerald-50"
          )}
          onClick={() => onStepClick(step.id)}
        >
          <div className="text-xs text-muted-foreground">Шаг {step.id}</div>
          <div className="font-medium">{step.title}</div>
          <div className="text-xs text-muted-foreground">{step.description}</div>
        </button>
      );
    })}
  </div>
));
