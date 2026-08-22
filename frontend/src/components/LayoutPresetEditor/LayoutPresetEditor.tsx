import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { apiClient } from "@/api/client";
import { listLayoutPresets, type LayoutPresetDto } from "@/api/branding";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TokenHelp } from "./TokenHelp";
import { PreviewModal } from "./PreviewModal";

type FormState = {
  code: string;
  name: string;
  different_first: boolean;
  different_odd_even: boolean;
  header_first_xml: string;
  header_odd_xml: string;
  header_even_xml: string;
  footer_first_xml: string;
  footer_odd_xml: string;
  footer_even_xml: string;
  watermark_text: string;
  watermark_enabled: boolean;
};

const emptyForm: FormState = {
  code: "",
  name: "",
  different_first: false,
  different_odd_even: false,
  header_first_xml: "",
  header_odd_xml:
    "{{organization.short_name}}\n{{organization.legal_address}}\nСтр. {PAGE}/{NUMPAGES}",
  header_even_xml: "",
  footer_first_xml: "",
  footer_odd_xml: "{{doc.passport}}",
  footer_even_xml: "",
  watermark_text: "",
  watermark_enabled: false,
};

const mapPresetToForm = (preset?: LayoutPresetDto | null): FormState => {
  if (!preset) return emptyForm;
  return {
    code: preset.code,
    name: preset.name,
    different_first: preset.different_first,
    different_odd_even: preset.different_odd_even,
    header_first_xml: preset.header_first_xml ?? "",
    header_odd_xml: preset.header_odd_xml ?? "",
    header_even_xml: preset.header_even_xml ?? "",
    footer_first_xml: preset.footer_first_xml ?? "",
    footer_odd_xml: preset.footer_odd_xml ?? "",
    footer_even_xml: preset.footer_even_xml ?? "",
    watermark_text: String(
      (preset.watermark?.text as string | undefined) ?? "",
    ),
    watermark_enabled: Boolean(preset.watermark?.enabled),
  };
};

export const LayoutPresetEditor = () => {
  const didPickDefaultSelectionRef = useRef(false);
  const [presets, setPresets] = useState<LayoutPresetDto[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [form, setForm] = useState<FormState>(emptyForm);
  const [preview, setPreview] = useState<{
    warnings: string[];
    unresolved: string[];
  }>({
    warnings: [],
    unresolved: [],
  });

  const selectedPreset = useMemo(
    () => presets.find((item) => item.id === selectedId) ?? null,
    [presets, selectedId],
  );

  const loadPresets = useCallback(async (selectCode?: string) => {
    const items = await listLayoutPresets();
    setPresets(items);
    if (selectCode) {
      const match = items.find((p) => p.code === selectCode);
      if (match) {
        setSelectedId(match.id);
      }
      return;
    }
    setSelectedId((prev) => {
      if (prev !== "") {
        return prev;
      }
      if (!didPickDefaultSelectionRef.current && items[0]) {
        didPickDefaultSelectionRef.current = true;
        return items[0].id;
      }
      return prev;
    });
  }, []);

  useEffect(() => {
    loadPresets().catch(() =>
      toast.error("Не удалось загрузить список пресетов"),
    );
  }, [loadPresets]);

  useEffect(() => {
    setForm(mapPresetToForm(selectedPreset));
  }, [selectedPreset]);

  const payload = {
    code: form.code,
    name: form.name,
    different_first: form.different_first,
    different_odd_even: form.different_odd_even,
    header_first_xml: form.header_first_xml || null,
    header_odd_xml: form.header_odd_xml || null,
    header_even_xml: form.header_even_xml || null,
    footer_first_xml: form.footer_first_xml || null,
    footer_odd_xml: form.footer_odd_xml || null,
    footer_even_xml: form.footer_even_xml || null,
    watermark: {
      enabled: form.watermark_enabled,
      text: form.watermark_text || null,
    },
  };

  const save = async () => {
    if (!form.code || !form.name) {
      toast.error("Укажите code и name");
      return;
    }
    try {
      if (selectedPreset) {
        await apiClient.patch(`/layout-presets/${selectedPreset.id}`, payload);
        toast.success("Пресет обновлён");
        await loadPresets();
      } else {
        await apiClient.post("/layout-presets", payload);
        toast.success("Пресет создан");
        await loadPresets(payload.code);
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Не удалось сохранить пресет",
      );
    }
  };

  const runPreview = async () => {
    const unresolved = [
      ...([
        form.header_first_xml,
        form.header_odd_xml,
        form.header_even_xml,
        form.footer_first_xml,
        form.footer_odd_xml,
        form.footer_even_xml,
      ]
        .join("\n")
        .match(/\{\{[^}]+\}\}/g) ?? []),
    ];
    setPreview({
      warnings: [
        form.different_odd_even
          ? "even/odd mode enabled"
          : "single odd/default mode",
        form.watermark_enabled
          ? `watermark=${form.watermark_text || "enabled"}`
          : "watermark disabled",
      ],
      unresolved,
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-[0.75fr_1.25fr]">
        <div className="space-y-2">
          <Label>Существующие пресеты</Label>
          <select
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            <option value="">Новый пресет</option>
            {presets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.code} — {preset.name}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <Label>code</Label>
            <Input
              value={form.code}
              onChange={(e) => setForm((s) => ({ ...s, code: e.target.value }))}
            />
          </div>
          <div>
            <Label>name</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <Label>Шапка (нечётная/по умолчанию)</Label>
          <Textarea
            value={form.header_odd_xml}
            onChange={(e) =>
              setForm((s) => ({ ...s, header_odd_xml: e.target.value }))
            }
            rows={5}
          />
        </div>
        <div>
          <Label>Подвал (нечётная/по умолчанию)</Label>
          <Textarea
            value={form.footer_odd_xml}
            onChange={(e) =>
              setForm((s) => ({ ...s, footer_odd_xml: e.target.value }))
            }
            rows={5}
          />
        </div>
      </div>

      {/* UX-бюджет (ТЗ разд. 59.2): пресету достаточно кода, имени и пары
          шапка/подвал по умолчанию. Отдельные варианты первой и чётной
          страницы имеют смысл только при включённых different first /
          different odd/even, водяной знак — тоже опция, поэтому весь этот
          хвост живёт под «Дополнительно», как в форме инцидента. */}
      <details className="space-y-1.5">
        <summary className="cursor-pointer text-sm text-muted-foreground">
          Дополнительно
        </summary>
        <div className="space-y-3 pt-3">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.different_first}
                onChange={(e) =>
                  setForm((s) => ({ ...s, different_first: e.target.checked }))
                }
              />
              different first page
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.different_odd_even}
                onChange={(e) =>
                  setForm((s) => ({
                    ...s,
                    different_odd_even: e.target.checked,
                  }))
                }
              />
              different odd/even
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <Label>Шапка (первая)</Label>
              <Textarea
                value={form.header_first_xml}
                onChange={(e) =>
                  setForm((s) => ({ ...s, header_first_xml: e.target.value }))
                }
                rows={4}
              />
            </div>
            <div>
              <Label>Подвал (первая)</Label>
              <Textarea
                value={form.footer_first_xml}
                onChange={(e) =>
                  setForm((s) => ({ ...s, footer_first_xml: e.target.value }))
                }
                rows={4}
              />
            </div>
            <div>
              <Label>Шапка (чётная)</Label>
              <Textarea
                value={form.header_even_xml}
                onChange={(e) =>
                  setForm((s) => ({ ...s, header_even_xml: e.target.value }))
                }
                rows={4}
              />
            </div>
            <div>
              <Label>Подвал (чётная)</Label>
              <Textarea
                value={form.footer_even_xml}
                onChange={(e) =>
                  setForm((s) => ({ ...s, footer_even_xml: e.target.value }))
                }
                rows={4}
              />
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.watermark_enabled}
                onChange={(e) =>
                  setForm((s) => ({
                    ...s,
                    watermark_enabled: e.target.checked,
                  }))
                }
              />
              watermark enabled
            </label>
            <Input
              value={form.watermark_text}
              onChange={(e) =>
                setForm((s) => ({ ...s, watermark_text: e.target.value }))
              }
              placeholder="ЧЕРНОВИК"
            />
          </div>
        </div>
      </details>

      <TokenHelp />
      <div className="flex gap-2">
        <Button onClick={() => void save()}>Сохранить пресет</Button>
        <Button variant="outline" onClick={() => void runPreview()}>
          Проверить токены
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            setSelectedId("");
            setForm(emptyForm);
          }}
        >
          Новый
        </Button>
      </div>
      <PreviewModal
        warnings={preview.warnings}
        unresolved={preview.unresolved}
      />
    </div>
  );
};
