import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { toast } from "sonner";

import {
  deleteOwnBrandImage,
  getOwnAppBranding,
  saveOwnAppBranding,
  uploadOwnBrandImage,
  type TenantBrandingDto,
} from "@/api/appBrand";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useBrandStore } from "@/stores/brand";

/**
 * Настройка бренда партнёра (ТЗ Доп. №1 разд. 52.2).
 *
 * Срезы 4 и 6 научили приложение НОСИТЬ бренд — имя, цвет, логотип, favicon.
 * Настроить его при этом было можно только запросом из консоли: функции
 * `getOwnAppBranding`/`saveOwnAppBranding` не вызывались ниоткуда, а загрузки
 * картинок на фронте не было вовсе. Партнёр, купивший платформу, не мог
 * перебрендировать её без curl — то есть работа была сделана наполовину.
 *
 * Полей ровно пять при бюджете экрана в семь (BIZ-59): имя, цвет, почта
 * поддержки и две картинки.
 */

/** Цвет храним HSL-триплетом, как ждёт переменная `--primary`, но человеку
 *  показываем обычный выбор цвета. Перевод живёт здесь и только здесь. */
const HSL_TRIPLET = /^(\d{1,3}(?:\.\d+)?)\s+(\d{1,3}(?:\.\d+)?)%\s+(\d{1,3}(?:\.\d+)?)%$/;

export const hslTripletToHex = (triplet: string): string => {
  const match = HSL_TRIPLET.exec(triplet.trim());
  if (!match) return "#000000";
  const [h, s, l] = [Number(match[1]), Number(match[2]) / 100, Number(match[3]) / 100];
  const chroma = (1 - Math.abs(2 * l - 1)) * s;
  const x = chroma * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - chroma / 2;
  const [r, g, b] = (
    h < 60
      ? [chroma, x, 0]
      : h < 120
        ? [x, chroma, 0]
        : h < 180
          ? [0, chroma, x]
          : h < 240
            ? [0, x, chroma]
            : h < 300
              ? [x, 0, chroma]
              : [chroma, 0, x]
  ).map((channel) => Math.round((channel + m) * 255));
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
};

/** Два знака после запятой, без хвостовых нулей.
 *
 *  Целые проценты выглядели бы аккуратнее, но округление до них смещает цвет:
 *  выбранный `#1e293b` возвращался с сервера как `#1d283a`. Человек видел бы,
 *  что «цвет не сохраняется», и при каждой правке оттенок уползал бы дальше.
 *  Дробные доли сервер принимает — его же умолчание `222.2 47.4% 11.2%`. */
const trim = (value: number): string => String(Math.round(value * 100) / 100);

export const hexToHslTriplet = (hex: string): string => {
  const clean = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(clean.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  let h = 0;
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
  }
  h *= 60;
  if (h < 0) h += 360;
  return `${trim(h)} ${trim(s * 100)}% ${trim(l * 100)}%`;
};

const PLATFORM_HINT = "не задано — действует бренд платформы";

const BrandSettingsPage = () => {
  const [data, setData] = useState<TenantBrandingDto | null>(null);
  const [appName, setAppName] = useState("");
  const [color, setColor] = useState("#1e293b");
  const [supportEmail, setSupportEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [denied, setDenied] = useState(false);
  const resetBrand = useBrandStore((state) => state.reset);

  /** Взять выбранный файл и сразу очистить поле.
   *
   *  Без очистки повторный выбор ТОГО ЖЕ файла браузер не считает изменением и
   *  события не шлёт: человек, поправивший логотип на диске и выбравший его
   *  снова, не понял бы, почему ничего не произошло. */
  const takeFile = (event: ChangeEvent<HTMLInputElement>): File | null => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    return file;
  };

  const load = useCallback(async () => {
    try {
      const loaded = await getOwnAppBranding();
      setData(loaded);
      setAppName(loaded.app_name ?? "");
      setSupportEmail(loaded.support_email ?? "");
      setColor(hslTripletToHex(loaded.primary_color ?? loaded.effective.primary_color));
    } catch {
      // Кабинет бренда открыт владельцу платформы и партнёру; клиенту сервер
      // отвечает отказом — показываем это состоянием, а не пустой формой.
      setDenied(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await saveOwnAppBranding({
        // Пустая строка — это «не задано», а не «пустое имя»: наследование
        // должно вернуться, а не оставить приложение без названия.
        app_name: appName.trim() || null,
        primary_color: hexToHslTriplet(color),
        support_email: supportEmail.trim() || null,
      });
      toast.success("Бренд сохранён");
      // Хранилище кэширует бренд на сеанс — без сброса человек не увидит
      // собственную правку до перезагрузки страницы.
      resetBrand();
      await load();
    } catch {
      /* сообщение уже показал общий перехватчик запросов */
    } finally {
      setSaving(false);
    }
  };

  const upload = async (kind: "logo" | "favicon", file: File) => {
    try {
      await uploadOwnBrandImage(kind, file);
      toast.success(kind === "logo" ? "Логотип загружен" : "Значок загружен");
      resetBrand();
      await load();
    } catch {
      /* сообщение уже показал общий перехватчик запросов */
    }
  };

  const drop = async (kind: "logo" | "favicon") => {
    try {
      await deleteOwnBrandImage(kind);
      toast.success("Картинка убрана");
      resetBrand();
      await load();
    } catch {
      /* сообщение уже показал общий перехватчик запросов */
    }
  };

  if (denied) {
    return (
      <div className="space-y-4">
        <RegistryPageHeader
          title="Бренд"
          description="Оформление приложения под вашу компанию."
        />
        <p className="text-sm text-muted-foreground">
          Раздел доступен владельцу платформы и партнёрам.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <RegistryPageHeader
        title="Бренд"
        description="Как приложение выглядит для вас и ваших клиентов."
        actions={
          <Button onClick={() => void save()} disabled={saving}>
            {saving ? "Сохранение..." : "Сохранить"}
          </Button>
        }
      />

      <div className="grid max-w-xl gap-4">
        <div className="space-y-2">
          <Label htmlFor="brand-name">Название приложения</Label>
          <Input
            id="brand-name"
            value={appName}
            placeholder={data?.effective.app_name ?? ""}
            onChange={(event) => setAppName(event.target.value)}
          />
          {/* Человек должен видеть, что покажется, если он оставит поле пустым —
              иначе «пусто» читается как «приложение без названия». */}
          <p className="text-xs text-muted-foreground">
            {data?.app_name
              ? `Сейчас: ${data.effective.app_name}`
              : `${PLATFORM_HINT} — «${data?.effective.app_name ?? ""}»`}
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="brand-color">Основной цвет</Label>
          <Input
            id="brand-color"
            type="color"
            className="h-10 w-24 p-1"
            value={color}
            onChange={(event) => setColor(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="brand-support">Почта поддержки</Label>
          <Input
            id="brand-support"
            type="email"
            value={supportEmail}
            onChange={(event) => setSupportEmail(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="brand-logo">Логотип</Label>
          <div className="flex items-center gap-2">
            <input
              id="brand-logo"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="text-sm"
              onChange={(event) => {
                const file = takeFile(event);
                if (file) void upload("logo", file);
              }}
            />
            {data?.has_logo ? (
              <Button variant="ghost" size="sm" onClick={() => void drop("logo")}>
                Убрать
              </Button>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">
            PNG, JPEG или WebP, до 512 КБ. SVG не принимается.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="brand-favicon">Значок вкладки</Label>
          <div className="flex items-center gap-2">
            <input
              id="brand-favicon"
              type="file"
              accept="image/png,image/x-icon,.ico"
              className="text-sm"
              onChange={(event) => {
                const file = takeFile(event);
                if (file) void upload("favicon", file);
              }}
            />
            {data?.has_favicon ? (
              <Button variant="ghost" size="sm" onClick={() => void drop("favicon")}>
                Убрать
              </Button>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">
            PNG или ICO, до 128 КБ. WebP не подходит: его иконки не понимает Safari.
          </p>
        </div>
      </div>
    </div>
  );
};

export default BrandSettingsPage;
