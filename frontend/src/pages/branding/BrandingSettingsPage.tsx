import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  getBrandingHistory,
  getBrandingProfile,
  listLayoutPresets,
  listSites,
  previewBranding,
  updateBrandingProfile,
  type BrandingGenerationHistoryItemDto,
  type BrandingPreviewDto,
  type BrandingProfileDto,
  type LayoutPresetDto,
  type SiteDto
} from "@/api/branding";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { useCompaniesStore } from "@/stores/companies";

const splitLines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

const parseJsonSafe = <T,>(value: string, fallback: T): T => {
  if (!value.trim()) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    throw new Error("Некорректный JSON в метаданных или подписантах");
  }
};

const BrandingSettingsPage = () => {
  const { items: companies, list } = useCompaniesStore();
  const [companyId, setCompanyId] = useState<string>("");
  const [siteId, setSiteId] = useState<string>("");
  const [sites, setSites] = useState<SiteDto[]>([]);
  const [presets, setPresets] = useState<LayoutPresetDto[]>([]);
  const [profile, setProfile] = useState<BrandingProfileDto | null>(null);
  const [preview, setPreview] = useState<BrandingPreviewDto | null>(null);
  const [previewHistory, setPreviewHistory] = useState<BrandingPreviewDto[]>([]);
  const [generationHistory, setGenerationHistory] = useState<BrandingGenerationHistoryItemDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [savedFingerprint, setSavedFingerprint] = useState<string>("");
  const [form, setForm] = useState({
    legal_name: "",
    short_name: "",
    inn: "",
    kpp: "",
    ogrn: "",
    legal_address: "",
    actual_address: "",
    website: "",
    email: "",
    branch_label: "",
    phones: "",
    header_details: "",
    footer_details: "",
    service_notes: "",
    passport_label: "",
    watermark_text: "",
    watermark_enabled: false,
    preferred_header_preset_code: "",
    logo_file_id: "",
    stamp_file_id: "",
    signature_file_id: "",
    palette_primary: "",
    palette_secondary: "",
    palette_accent: "",
    metadata_json: "{}",
    signatories_json: "[]"
  });

  useEffect(() => {
    list().catch(() => undefined);
    listLayoutPresets()
      .then(setPresets)
      .catch(() => toast.error("Не удалось загрузить layout presets"));
  }, [list]);

  useEffect(() => {
    if (!companyId && companies.length > 0) {
      setCompanyId(companies[0].id);
    }
  }, [companies, companyId]);

  useEffect(() => {
    if (!companyId) {
      setSites([]);
      setSiteId("");
      return;
    }
    listSites(companyId)
      .then((items) => setSites(items))
      .catch(() => {
        setSites([]);
        toast.error("Не удалось загрузить филиалы/объекты");
      });
  }, [companyId]);

  useEffect(() => {
    if (!companyId) return;
    setLoading(true);
    Promise.all([
      getBrandingProfile(companyId, siteId || undefined),
      getBrandingHistory(companyId, siteId || undefined, 10).catch(() => [])
    ])
      .then(([data, history]) => {
        const nextForm = {
          legal_name: data.branding.legal_name ?? "",
          short_name: data.branding.short_name ?? "",
          inn: data.branding.inn ?? "",
          kpp: data.branding.kpp ?? "",
          ogrn: data.branding.ogrn ?? "",
          legal_address: data.branding.legal_address ?? "",
          actual_address: data.branding.actual_address ?? "",
          website: data.branding.website ?? "",
          email: data.branding.email ?? "",
          branch_label: data.branding.branch_label ?? "",
          phones: data.branding.phones.join("\n"),
          header_details: data.branding.header_details.join("\n"),
          footer_details: data.branding.footer_details.join("\n"),
          service_notes: data.branding.service_notes.join("\n"),
          passport_label: data.branding.passport_label ?? "",
          watermark_text: data.branding.watermark_text ?? "",
          watermark_enabled: data.branding.watermark_enabled,
          preferred_header_preset_code:
            data.preferred_header_preset_code ?? data.branding.preferred_letterhead_preset ?? "",
          logo_file_id: data.branding.images?.logo_file_id ?? "",
          stamp_file_id: data.branding.images?.stamp_file_id ?? "",
          signature_file_id: data.branding.images?.signature_file_id ?? "",
          palette_primary: data.branding.palette?.primary ?? "",
          palette_secondary: data.branding.palette?.secondary ?? "",
          palette_accent: data.branding.palette?.accent ?? "",
          metadata_json: JSON.stringify(data.branding.metadata ?? {}, null, 2),
          signatories_json: JSON.stringify(data.branding.signatories ?? [], null, 2)
        };
        setGenerationHistory(history);
        setProfile(data);
        setPreview(null);
        setForm(nextForm);
        setSavedFingerprint(JSON.stringify({ companyId, siteId, form: nextForm }));
      })
      .catch(() => toast.error("Не удалось загрузить branding profile"))
      .finally(() => setLoading(false));
  }, [companyId, siteId]);

  const currentCompany = useMemo(
    () => companies.find((item) => item.id === companyId),
    [companies, companyId]
  );
  const currentSite = useMemo(() => sites.find((item) => item.id === siteId), [siteId, sites]);
  const currentFingerprint = useMemo(
    () => JSON.stringify({ companyId, siteId, form }),
    [companyId, form, siteId],
  );
  const hasUnsavedChanges = Boolean(profile) && !loading && currentFingerprint !== savedFingerprint;

  useUnsavedChanges(hasUnsavedChanges);

  const handleSave = async () => {
    if (!companyId) return;
    try {
      const payload = {
        preferred_header_preset_code: form.preferred_header_preset_code || null,
        site_id: siteId || null,
        branding: {
          legal_name: form.legal_name,
          short_name: form.short_name,
          inn: form.inn,
          kpp: form.kpp,
          ogrn: form.ogrn,
          legal_address: form.legal_address,
          actual_address: form.actual_address,
          website: form.website,
          email: form.email,
          branch_label: form.branch_label,
          phones: splitLines(form.phones),
          header_details: splitLines(form.header_details),
          footer_details: splitLines(form.footer_details),
          service_notes: splitLines(form.service_notes),
          passport_label: form.passport_label,
          preferred_letterhead_preset: form.preferred_header_preset_code || null,
          watermark_text: form.watermark_text,
          watermark_enabled: form.watermark_enabled,
          contacts: profile?.branding.contacts ?? [],
          images: {
            logo_file_id: form.logo_file_id || null,
            stamp_file_id: form.stamp_file_id || null,
            signature_file_id: form.signature_file_id || null
          },
          palette: {
            primary: form.palette_primary || null,
            secondary: form.palette_secondary || null,
            accent: form.palette_accent || null
          },
          metadata: parseJsonSafe<Record<string, unknown>>(form.metadata_json, {}),
          signatories: parseJsonSafe<Array<Record<string, unknown>>>(form.signatories_json, [])
        }
      };
      const saved = await updateBrandingProfile(companyId, payload);
      setProfile(saved);
      setSavedFingerprint(currentFingerprint);
      toast.success(siteId ? "Брендинг филиала сохранён" : "Фирменный профиль организации сохранён");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось сохранить профиль");
    }
  };

  const handlePreview = async () => {
    if (!companyId) return;
    const result = await previewBranding({
      company_id: companyId,
      site_id: siteId || undefined,
      preset_code: form.preferred_header_preset_code || undefined,
      document_title: "Приказ по охране труда",
      document_number: currentSite ? "OT-BRANCH-2026-001" : "OT-2026-001",
      watermark_override: form.watermark_enabled ? { text: form.watermark_text || undefined } : { enabled: false }
    });
    setPreview(result);
    setPreviewHistory((prev) => [result, ...prev].slice(0, 5));
    toast.success("Предпросмотр обновлён");
  };

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Документы", to: "/documents" },
          { label: "Фирменные бланки" }
        ]}
      />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Branding / letterhead settings</h1>
          <p className="text-sm text-muted-foreground">
            Tenant-safe профиль организации/филиала, быстрый preview колонтитулов и паспорт воспроизводимости.
          </p>
        </div>
        <div className="grid w-full gap-4 lg:max-w-3xl lg:grid-cols-2">
          <div>
            <Label>Организация</Label>
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={companyId}
              onChange={(event) => {
                setCompanyId(event.target.value);
                setSiteId("");
              }}
            >
              <option value="">Выберите организацию</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Филиал / объект</Label>
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={siteId}
              onChange={(event) => setSiteId(event.target.value)}
            >
              <option value="">Уровень организации</option>
              {sites.map((site) => (
                <option key={site.id} value={site.id}>
                  {site.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <Card>
        <CardContent className="grid gap-4 pt-6 md:grid-cols-4">
          <div>
            <div className="text-sm text-muted-foreground">Текущий scope</div>
            <div className="font-medium">{profile?.scope ?? "—"}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Организация</div>
            <div className="font-medium">{currentCompany?.name ?? "—"}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Филиал / объект</div>
            <div className="font-medium">{currentSite?.name ?? "—"}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Активный preset</div>
            <div className="font-medium">{profile?.preferred_header_preset_code ?? "—"}</div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle>Профиль брендинга и реквизитов</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              {[
                ["Полное название", "legal_name"],
                ["Краткое название", "short_name"],
                ["ИНН", "inn"],
                ["КПП", "kpp"],
                ["ОГРН", "ogrn"],
                ["Email", "email"],
                ["Website", "website"],
                ["Метка филиала", "branch_label"]
              ].map(([label, key]) => (
                <div key={key}>
                  <Label>{label}</Label>
                  <Input
                    value={form[key as keyof typeof form] as string}
                    onChange={(e) => setForm((s) => ({ ...s, [key]: e.target.value }))}
                  />
                </div>
              ))}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Юридический адрес</Label>
                <Textarea
                  rows={3}
                  value={form.legal_address}
                  onChange={(e) => setForm((s) => ({ ...s, legal_address: e.target.value }))}
                />
              </div>
              <div>
                <Label>Фактический адрес</Label>
                <Textarea
                  rows={3}
                  value={form.actual_address}
                  onChange={(e) => setForm((s) => ({ ...s, actual_address: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Телефоны</Label>
                <Textarea
                  rows={4}
                  value={form.phones}
                  onChange={(e) => setForm((s) => ({ ...s, phones: e.target.value }))}
                />
              </div>
              <div>
                <Label>Реквизиты в шапке</Label>
                <Textarea
                  rows={4}
                  value={form.header_details}
                  onChange={(e) => setForm((s) => ({ ...s, header_details: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Реквизиты в подвале</Label>
                <Textarea
                  rows={4}
                  value={form.footer_details}
                  onChange={(e) => setForm((s) => ({ ...s, footer_details: e.target.value }))}
                />
              </div>
            </div>

            <div>
              <Label>Служебные надписи / примечания по ветке</Label>
              <Textarea
                rows={3}
                value={form.service_notes}
                onChange={(e) => setForm((s) => ({ ...s, service_notes: e.target.value }))}
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Паспорт документа</Label>
                <Input
                  value={form.passport_label}
                  onChange={(e) => setForm((s) => ({ ...s, passport_label: e.target.value }))}
                />
              </div>
              <div>
                <Label>Preset колонтитулов</Label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={form.preferred_header_preset_code}
                  onChange={(e) =>
                    setForm((s) => ({ ...s, preferred_header_preset_code: e.target.value }))
                  }
                >
                  <option value="">Использовать preset по умолчанию</option>
                  {presets.map((preset) => (
                    <option key={preset.id} value={preset.code}>
                      {preset.code} — {preset.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <Separator />
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <Label>ID файла логотипа</Label>
                <Input
                  value={form.logo_file_id}
                  onChange={(e) => setForm((s) => ({ ...s, logo_file_id: e.target.value }))}
                />
              </div>
              <div>
                <Label>ID файла печати</Label>
                <Input
                  value={form.stamp_file_id}
                  onChange={(e) => setForm((s) => ({ ...s, stamp_file_id: e.target.value }))}
                />
              </div>
              <div>
                <Label>ID файла подписи</Label>
                <Input
                  value={form.signature_file_id}
                  onChange={(e) => setForm((s) => ({ ...s, signature_file_id: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <Label>Основной цвет</Label>
                <Input
                  value={form.palette_primary}
                  onChange={(e) => setForm((s) => ({ ...s, palette_primary: e.target.value }))}
                  placeholder="#0055AA"
                />
              </div>
              <div>
                <Label>Дополнительный цвет</Label>
                <Input
                  value={form.palette_secondary}
                  onChange={(e) => setForm((s) => ({ ...s, palette_secondary: e.target.value }))}
                />
              </div>
              <div>
                <Label>Акцентный цвет</Label>
                <Input
                  value={form.palette_accent}
                  onChange={(e) => setForm((s) => ({ ...s, palette_accent: e.target.value }))}
                />
              </div>
            </div>

            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <div className="font-medium">Водяной знак</div>
                <div className="text-sm text-muted-foreground">
                  Черновик / служебный штамп в шапке. Учитывается в превью и попадает в метаданные воспроизводимости.
                </div>
              </div>
              <Switch
                checked={form.watermark_enabled}
                onCheckedChange={(checked) =>
                  setForm((s) => ({ ...s, watermark_enabled: checked }))
                }
              />
            </div>
            <div>
              <Label>Текст водяного знака</Label>
              <Input
                value={form.watermark_text}
                onChange={(e) => setForm((s) => ({ ...s, watermark_text: e.target.value }))}
                placeholder="DRAFT / FOR-APPROVAL"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Метаданные (JSON)</Label>
                <Textarea
                  rows={6}
                  value={form.metadata_json}
                  onChange={(e) => setForm((s) => ({ ...s, metadata_json: e.target.value }))}
                />
              </div>
              <div>
                <Label>Подписанты (JSON)</Label>
                <Textarea
                  rows={6}
                  value={form.signatories_json}
                  onChange={(e) => setForm((s) => ({ ...s, signatories_json: e.target.value }))}
                />
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void handleSave()}>Сохранить профиль</Button>
              <Button
                variant="outline"
                onClick={() => void handlePreview().catch(() => toast.error("Не удалось собрать превью"))}
              >
                Тестовая генерация превью с брендингом
              </Button>
            </div>
            {loading ? <div className="text-sm text-muted-foreground">Загрузка профиля…</div> : null}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Превью бланка</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-md border bg-muted/30 p-3 text-sm">
                <div className="font-medium">Шапка, нечётная страница</div>
                <div className="mt-2 whitespace-pre-wrap">{preview?.sections.header_odd ?? "Сначала выполните тестовую генерацию."}</div>
              </div>
              <div className="rounded-md border bg-muted/30 p-3 text-sm">
                <div className="font-medium">Шапка, чётная / первая</div>
                <div className="mt-2 whitespace-pre-wrap">{preview?.sections.header_even ?? preview?.sections.header_first ?? "—"}</div>
              </div>
              <div className="rounded-md border bg-muted/30 p-3 text-sm">
                <div className="font-medium">Подвал, нечётная страница</div>
                <div className="mt-2 whitespace-pre-wrap">{preview?.sections.footer_odd ?? "—"}</div>
              </div>
              <div className="rounded-md border bg-muted/30 p-3 text-sm">
                <div className="font-medium">Итоговый водяной знак</div>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs">{JSON.stringify(preview?.watermark ?? {}, null, 2)}</pre>
              </div>
              <div className="rounded-md border bg-muted/30 p-3 text-sm">
                <div className="font-medium">Цепочка разрешения / источник пресета</div>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs">
                  {JSON.stringify(preview?.profile.resolution ?? profile?.resolution ?? {}, null, 2)}
                </pre>
              </div>
              {preview?.unresolved_placeholders?.length ? (
                <div className="text-sm text-amber-700">
                  Незаполненные плейсхолдеры: {preview.unresolved_placeholders.join(", ")}
                </div>
              ) : (
                <div className="text-sm text-green-700">Все placeholders разрешены.</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Паспорт воспроизводимости</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="overflow-x-auto rounded-md bg-muted/30 p-3 text-xs">
                {JSON.stringify(preview?.profile.reproducibility ?? profile?.reproducibility ?? {}, null, 2)}
              </pre>
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>История branded generation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {generationHistory.length === 0 ? (
                <div className="text-muted-foreground">Серверная история появится после запуска single pipeline из document wizard.</div>
              ) : (
                generationHistory.map((item) => (
                  <div key={item.pipeline_run_id} className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-medium">{item.document_title ?? "Документ"}</div>
                      <div className="text-xs text-muted-foreground">{item.generated_at ?? "unknown"}</div>
                    </div>
                    <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
                      <div>pipeline_run_id={item.pipeline_run_id}</div>
                      <div>status={item.status}</div>
                      <div>preset={item.preset_code ?? "auto"}</div>
                      <div>number={item.document_number ?? "—"}</div>
                    </div>
                    <pre className="mt-3 overflow-x-auto rounded-md border bg-muted/30 p-2 text-[11px]">
                      {JSON.stringify(item.reproducibility ?? {}, null, 2)}
                    </pre>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>История последних preview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {previewHistory.length === 0 ? (
                <div className="text-sm text-muted-foreground">История появится после тестовых генераций.</div>
              ) : (
                previewHistory.map((item, index) => (
                  <div key={`${item.profile.reproducibility.generated_at}-${index}`} className="rounded-md border p-3 text-sm">
                    <div className="font-medium">{String(item.profile.reproducibility.generated_at ?? "unknown")}</div>
                    <div className="text-muted-foreground">
                      preset={item.preset_code ?? "—"}, scope={item.profile.scope}, watermark={String(item.watermark.text ?? "off")}
                    </div>
                    <div className="mt-2 whitespace-pre-wrap text-xs">{item.sections.header_odd ?? "—"}</div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default BrandingSettingsPage;
