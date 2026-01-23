import { useMemo } from "react";
import { Building, FileText, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/common/StatusBadge";
import { formatDate } from "@/utils/datetime";
import { usePacksStore } from "@/stores/packs";
import type { CompanyDto } from "@/types/dto/companies";
import type { PackPreset } from "@/types/dto/packs";

const packPresets: { label: string; value: PackPreset }[] = [
  { label: "Выход на объект", value: "site_entry" },
  { label: "Несчастный случай", value: "incident_response" },
  { label: "Пожарная безопасность", value: "fire_safety" },
  { label: "Экология", value: "environmental" }
];

export const CompanyDetails = ({ company }: { company: CompanyDto }) => {
  const { create } = usePacksStore();

  const tags = useMemo(() => company.tags ?? [], [company.tags]);

  const handleGeneratePack = async (preset: PackPreset) => {
    await create({ company_id: company.id, preset, parameters: {} });
  };

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 text-2xl font-semibold">
            <Building className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
            {company.name}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <StatusBadge status={company.status} />
            <span>ИНН {company.inn}</span>
            {company.kpp && <span>КПП {company.kpp}</span>}
            <span>Обновлено {formatDate(company.updated_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {packPresets.map((preset) => (
            <Button key={preset.value} variant="outline" size="sm" onClick={() => handleGeneratePack(preset.value)}>
              Сгенерировать: {preset.label}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="details">
          <TabsList>
            <TabsTrigger value="details">
              <Building className="mr-2 h-4 w-4" aria-hidden="true" /> Реквизиты
            </TabsTrigger>
            <TabsTrigger value="people">
              <Users className="mr-2 h-4 w-4" aria-hidden="true" /> Сотрудники
            </TabsTrigger>
            <TabsTrigger value="documents">
              <FileText className="mr-2 h-4 w-4" aria-hidden="true" /> Документы
            </TabsTrigger>
          </TabsList>
          <TabsContent value="details" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <InfoRow label="Адрес" value={company.address} />
              <InfoRow label="Email" value={company.email} />
              <InfoRow label="Телефон" value={company.phone} />
              <InfoRow label="Сайт" value={company.website} />
            </div>
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {tags.map((tag) => (
                  <Badge key={tag} variant="secondary">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </TabsContent>
          <TabsContent value="people" className="space-y-4">
            {company.persons?.length ? (
              <ul className="space-y-2">
                {company.persons.map((person) => (
                  <li key={person.id} className="rounded-md border p-3">
                    <div className="font-medium">{person.full_name}</div>
                    <div className="text-sm text-muted-foreground">{person.position}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Сотрудники не привязаны.</p>
            )}
          </TabsContent>
          <TabsContent value="documents" className="space-y-4">
            {company.documents?.length ? (
              <ul className="space-y-2">
                {company.documents.map((document) => (
                  <li key={document.id} className="rounded-md border p-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium">{document.name}</div>
                        <div className="text-xs text-muted-foreground">Версия {document.version}</div>
                      </div>
                      <StatusBadge status={document.status} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Документы не найдены.</p>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};

const InfoRow = ({ label, value }: { label: string; value?: string | null }) => (
  <div>
    <div className="text-xs uppercase text-muted-foreground">{label}</div>
    <div className="text-sm font-medium text-foreground">{value || "—"}</div>
  </div>
);
