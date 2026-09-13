import { useEffect, useMemo, useState } from "react";
import { Building, FileText, Loader2, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/common/StatusBadge";
import { fetchPersonsForCompany } from "@/api/personsApi";
import { usePersonsStore } from "@/stores/persons";
import { formatDate } from "@/utils/datetime";
import { useCompaniesStore } from "@/stores/companies";
import type { CompanyDto } from "@/types/dto/companies";
import type { PersonDto } from "@/types/dto/persons";

export const CompanyDetails = ({ company }: { company: CompanyDto }) => {
  const personsRegistryRevision = usePersonsStore(
    (s) => s.personsRegistryRevision,
  );
  const [companyPeople, setCompanyPeople] = useState<PersonDto[]>(
    () => company.persons ?? [],
  );
  const [peopleLoading, setPeopleLoading] = useState(false);

  const tags = useMemo(() => company.tags ?? [], [company.tags]);

  // BIZ-53 (разд. 53.3): имя головной компании группы — по списку из стора.
  const companiesList = useCompaniesStore((s) => s.items);
  const parentName = company.parent_company_id
    ? (companiesList.find((c) => c.id === company.parent_company_id)?.name ??
      company.parent_company_id)
    : null;

  useEffect(() => {
    let cancelled = false;
    setCompanyPeople([]);
    setPeopleLoading(true);
    void fetchPersonsForCompany(company.id)
      .then((rows) => {
        if (!cancelled) setCompanyPeople(rows);
      })
      .catch(() => {
        if (!cancelled) setCompanyPeople(company.persons ?? []);
      })
      .finally(() => {
        if (!cancelled) setPeopleLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [company.id, company.persons, personsRegistryRevision]);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 text-2xl font-semibold">
            <Building
              className="h-5 w-5 text-muted-foreground"
              aria-hidden="true"
            />
            {company.name}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <StatusBadge status={company.status} />
            <span>ИНН {company.inn}</span>
            {company.kpp && <span>КПП {company.kpp}</span>}
            {parentName && <span>Группа: {parentName}</span>}
            <span>Обновлено {formatDate(company.updated_at)}</span>
          </div>
        </div>
        {/* Срез-153: четыре кнопки «Сгенерировать: …» слали запрос на
            `POST /packs` — ручки, которой у сервера нет вовсе (есть
            `/packs/run` с кодом сценария), да ещё и с собственным списком
            пресетов, не совпадающим ни с одним комплектом продукта. Нажатие
            всегда кончалось 404. Комплект собирается мастером, который знает
            сценарии с сервера; отсюда — переход с уже выбранной компанией. */}
        <Button asChild variant="outline" size="sm">
          <Link to={`/packs/wizard?company_id=${company.id}`}>
            Собрать комплект документов
          </Link>
        </Button>
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
              <InfoRow label="Электронная почта" value={company.email} />
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
            <p className="text-xs text-muted-foreground">
              Список подгружается из реестра сотрудников по выбранной
              организации.{" "}
              <Link to="/persons" className="underline underline-offset-2">
                Открыть раздел «Сотрудники»
              </Link>
            </p>
            {peopleLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Загрузка списка…
              </div>
            ) : companyPeople.length > 0 ? (
              <ul className="space-y-2">
                {companyPeople.map((person) => (
                  <li key={person.id} className="rounded-md border p-3">
                    <div className="font-medium">{person.full_name}</div>
                    <div className="text-sm text-muted-foreground">
                      {person.position ?? "—"}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                В этой организации пока нет сотрудников в реестре.
              </p>
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
                        <div className="text-xs text-muted-foreground">
                          Версия {document.version}
                        </div>
                      </div>
                      <StatusBadge status={document.status} />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                Документы не найдены.
              </p>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};

const InfoRow = ({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) => (
  <div>
    <div className="text-xs uppercase text-muted-foreground">{label}</div>
    <div className="text-sm font-medium text-foreground">{value || "—"}</div>
  </div>
);
