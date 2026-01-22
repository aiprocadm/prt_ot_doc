import { useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { TemplateDetails } from "@/features/templates/TemplateDetails";
import { TemplateFormDialog } from "@/features/templates/TemplateFormDialog";
import { TemplateTable } from "@/features/templates/TemplateTable";
import { useTemplatesStore } from "@/stores/templates";
import type { TemplateDto } from "@/types/dto/templates";

const TemplatesPage = () => {
  const { list } = useTemplatesStore();
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateDto | null>(null);

  useEffect(() => {
    list();
  }, [list]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Шаблоны" }]} />
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Шаблоны</h1>
          <TemplateFormDialog
            trigger={<Button>Добавить</Button>}
            onSubmitted={(template) => {
              setSelectedTemplate(template);
              list();
            }}
          />
        </div>
      </div>
      <Card>
        <CardContent className="py-6">
          <TemplateTable onSelect={setSelectedTemplate} />
        </CardContent>
      </Card>
      {selectedTemplate && <TemplateDetails template={selectedTemplate} />}
    </div>
  );
};

export default TemplatesPage;
