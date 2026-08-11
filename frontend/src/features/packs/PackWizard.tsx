import { useEffect, useState } from "react";
import { CheckCircle, ClipboardList, Factory, Settings2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCompaniesStore } from "@/stores/companies";
import { usePacksStore } from "@/stores/packs";
import type { PackPreset } from "@/types/dto/packs";

const presets: { label: string; value: PackPreset; description: string }[] = [
  { label: "Выход на объект", value: "site_entry", description: "Документы для допуска к объекту" },
  { label: "Несчастный случай", value: "incident_response", description: "Пакет при расследовании" },
  { label: "Пожарная безопасность", value: "fire_safety", description: "Регламенты и инструкции" },
  { label: "Экология", value: "environmental", description: "Экологическая документация" }
];

export const PackWizard = () => {
  const { items: companies, list: listCompanies } = useCompaniesStore();
  const { create } = usePacksStore();
  const [step, setStep] = useState(1);
  const [companyId, setCompanyId] = useState<string>("");
  const [preset, setPreset] = useState<PackPreset | "">("");
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    listCompanies();
  }, [listCompanies]);

  const handleLaunch = async () => {
    if (!companyId || !preset) {
      setSubmitError("Заполните обязательные шаги мастера перед запуском.");
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await create({ company_id: companyId, preset, parameters });
      toast.success("Задача на генерацию создана");
      setStep(4);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не удалось создать задачу генерации";
      setSubmitError(message);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetWizard = () => {
    setCompanyId("");
    setPreset("");
    setParameters({});
    setSubmitError(null);
    setStep(1);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl font-semibold">Мастер генерации пакета</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <StepIndicator step={1} current={step} label="Компания" icon={<Factory className="h-4 w-4" />} />
          <StepIndicator step={2} current={step} label="Пресет" icon={<ClipboardList className="h-4 w-4" />} />
          <StepIndicator step={3} current={step} label="Параметры" icon={<Settings2 className="h-4 w-4" />} />
          <StepIndicator step={4} current={step} label="Итог" icon={<CheckCircle className="h-4 w-4" />} />
        </div>
        {step === 1 && (
          <div className="space-y-4">
            <Label htmlFor="pack-company">Выберите компанию</Label>
            <select
              id="pack-company"
              className="h-10 rounded-md border px-3"
              value={companyId}
              onChange={(event) => setCompanyId(event.target.value)}
            >
              <option value="">—</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
            <Button disabled={!companyId} title={!companyId ? "Выберите компанию, чтобы продолжить" : undefined} onClick={() => setStep(2)}>
              Далее
            </Button>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-4">
            <Label>Пресет пакета</Label>
            <div className="grid gap-3 sm:grid-cols-2">
              {presets.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setPreset(option.value)}
                  className={`rounded-md border p-4 text-left transition ${
                    preset === option.value ? "border-primary bg-primary/5" : "hover:border-primary"
                  }`}
                >
                  <div className="font-medium">{option.label}</div>
                  <div className="text-xs text-muted-foreground">{option.description}</div>
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                Назад
              </Button>
              <Button disabled={!preset} title={!preset ? "Выберите пресет" : undefined} onClick={() => setStep(3)}>
                Далее
              </Button>
            </div>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-4">
            <Label htmlFor="param-notes">Дополнительные параметры</Label>
            <Input
              id="param-notes"
              placeholder="Например, номер объекта"
              value={parameters.notes ?? ""}
              onChange={(event) => setParameters((prev) => ({ ...prev, notes: event.target.value }))}
            />
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)}>
                Назад
              </Button>
              <Button disabled={isSubmitting} onClick={handleLaunch}>
                {isSubmitting ? "Запуск..." : "Запустить генерацию"}
              </Button>
            </div>
            {submitError && (
              <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive" role="alert">
                {submitError}
              </p>
            )}
          </div>
        )}
        {step === 4 && (
          <div className="space-y-2 text-sm" aria-live="polite">
            <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-emerald-700">Задача создана. Статус можно отслеживать в разделе «Задачи».</p>
            <Button variant="outline" onClick={resetWizard}>
              Создать ещё один пакет
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const StepIndicator = ({ step, current, label, icon }: { step: number; current: number; label: string; icon: React.ReactNode }) => (
  <div className={`flex items-center gap-2 rounded-full border px-3 py-1 ${step <= current ? "border-primary text-primary" : "border-muted-foreground/30"}`}>
    {icon}
    <span className="text-xs font-medium uppercase">{label}</span>
  </div>
);
