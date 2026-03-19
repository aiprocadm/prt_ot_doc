import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  getBrandingProfile,
  previewBranding,
  updateBrandingProfile,
  type BrandingProfileDto,
  type BrandingPreviewDto
} from "@/api/branding";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useCompaniesStore } from "@/stores/companies";

const splitLines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);

const BrandingSettingsPage = () => {
  const { items: companies, list } = useCompaniesStore();
  const [companyId, setCompanyId] = useState<string>("");
  const [profile, setProfile] = useState<BrandingProfileDto | null>(null);
  const [preview, setPreview] = useState<BrandingPreviewDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    legal_name: "",
    short_name: "",
    website: "",
    email: "",
    phones: "",
    footer_details: "",
    service_notes: "",
    passport_label: "",
    watermark_text: "",
    watermark_enabled: false,
    preferred_header_preset_code: "default"
  });

  useEffect(() => {
    list().catch(() => undefined);
  }, [list]);

  useEffect(() => {
    if (!companyId && companies.length > 0) {
      setCompanyId(companies[0].id);
    }
  }, [companies, companyId]);

  useEffect(() => {
    if (!companyId) return;
    setLoading(true);
    getBrandingProfile(companyId)
      .then((data) => {
        setProfile(data);
        setForm({
          legal_name: data.branding.legal_name ?? "",
          short_name: data.branding.short_name ?? "",
          website: data.branding.website ?? "",
          email: data.branding.email ?? "",
          phones: data.branding.phones.join("\n"),
          footer_details: data.branding.footer_details.join("\n"),
          service_notes: data.branding.service_notes.join("\n"),
          passport_label: data.branding.passport_label ?? "",
          watermark_text: data.branding.watermark_text ?? "",
          watermark_enabled: data.branding.watermark_enabled,
          preferred_header_preset_code:
            data.preferred_header_preset_code ?? data.branding.preferred_letterhead_preset ?? "default"
        });
      })
      .catch(() => toast.error("Не удалось загрузить branding profile"))
      .finally(() => setLoading(false));
  }, [companyId]);

  const currentCompany = useMemo(
    () => companies.find((item) => item.id === companyId),
    [companies, companyId]
  );

  const handleSave = async () => {
    if (!companyId) return;
    const payload = {
      preferred_header_preset_code:
        form.preferred_header_preset_code === "default"
          ? null
          : form.preferred_header_preset_code,
      branding: {
        legal_name: form.legal_name,
        short_name: form.short_name,
        website: form.website,
        email: form.email,
        phones: splitLines(form.phones),
        footer_details: splitLines(form.footer_details),
        service_notes: splitLines(form.service_notes),
        passport_label: form.passport_label,
        preferred_letterhead_preset:
          form.preferred_header_preset_code === "default"
            ? null
            : form.preferred_header_preset_code,
        watermark_text: form.watermark_text,
        watermark_enabled: form.watermark_enabled,
        contacts: profile?.branding.contacts ?? []
      }
    };
    const saved = await updateBrandingProfile(companyId, payload);
    setProfile(saved);
    toast.success("Фирменный профиль сохранён");
  };

  const handlePreview = async () => {
    if (!companyId) return;
    const result = await previewBranding({
      company_id: companyId,
      preset_code:
        form.preferred_header_preset_code === "default"
          ? undefined
          : form.preferred_header_preset_code,
      document_title: "Приказ по охране труда",
      document_number: "OT-2026-001"
    });
    setPreview(result);
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
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Branding / letterhead settings</h1>
          <p className="text-sm text-muted-foreground">
            Управление реквизитами, watermark и предпочитаемым фирменным бланком для
            конкретной организации.
          </p>
        </div>
        <div className="w-full max-w-sm">
          <Label>Организация</Label>
          <select
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={companyId}
            onChange={(event) => setCompanyId(event.target.value)}
          >
            <option value="">Выберите организацию</option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>Профиль брендинга</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Полное название</Label>
                <Input
                  value={form.legal_name}
                  onChange={(e) => setForm((s) => ({ ...s, legal_name: e.target.value }))}
                />
              </div>
              <div>
                <Label>Краткое название</Label>
                <Input
                  value={form.short_name}
                  onChange={(e) => setForm((s) => ({ ...s, short_name: e.target.value }))}
                />
              </div>
              <div>
                <Label>Email</Label>
                <Input
                  value={form.email}
                  onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))}
                />
              </div>
              <div>
                <Label>Website</Label>
                <Input
                  value={form.website}
                  onChange={(e) => setForm((s) => ({ ...s, website: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label>Телефоны</Label>
                <Textarea
                  value={form.phones}
                  onChange={(e) => setForm((s) => ({ ...s, phones: e.target.value }))}
                  rows={4}
                />
              </div>
              <div>
                <Label>Footer requisites</Label>
                <Textarea
                  value={form.footer_details}
                  onChange={(e) => setForm((s) => ({ ...s, footer_details: e.target.value }))}
                  rows={4}
                />
              </div>
            </div>

            <div>
              <Label>Служебные надписи / branch notes</Label>
              <Textarea
                value={form.service_notes}
                onChange={(e) => setForm((s) => ({ ...s, service_notes: e.target.value }))}
                rows={3}
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
                <Label>Preset code</Label>
                <Input
                  value={form.preferred_header_preset_code}
                  onChange={(e) =>
                    setForm((s) => ({ ...s, preferred_header_preset_code: e.target.value }))
                  }
                  placeholder="company_brand"
                />
              </div>
            </div>

            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <div className="font-medium">Watermark</div>
                <div className="text-sm text-muted-foreground">
                  Черновик / служебный штамп в header.
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
              <Label>Watermark text</Label>
              <Input
                value={form.watermark_text}
                onChange={(e) => setForm((s) => ({ ...s, watermark_text: e.target.value }))}
                placeholder="DRAFT / INTERNAL"
              />
            </div>

            <div className="flex gap-2">
              <Button
                onClick={() => handleSave().catch(() => toast.error("Не удалось сохранить профиль"))}
                disabled={!companyId || loading}
              >
                Сохранить профиль
              </Button>
              <Button
                variant="outline"
                onClick={() => handlePreview().catch(() => toast.error("Не удалось собрать preview"))}
                disabled={!companyId}
              >
                Тестовая генерация
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Preview / reproducibility</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div>
              <div className="font-medium">Организация</div>
              <div className="text-muted-foreground">{currentCompany?.name ?? "—"}</div>
            </div>
            <Separator />
            <div>
              <div className="font-medium">Metadata</div>
              <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">
                {JSON.stringify(profile?.reproducibility ?? {}, null, 2)}
              </pre>
            </div>
            <Separator />
            <div>
              <div className="font-medium">Header odd</div>
              <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                {preview?.sections.header_odd ?? "Сначала выполните тестовую генерацию."}
              </pre>
            </div>
            <div>
              <div className="font-medium">Footer odd</div>
              <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                {preview?.sections.footer_odd ?? "—"}
              </pre>
            </div>
            {preview?.unresolved_placeholders?.length ? (
              <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-900">
                Незаполненные placeholders: {preview.unresolved_placeholders.join(", ")}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default BrandingSettingsPage;
