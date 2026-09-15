import { useEffect, useState } from "react";

import { ssoApi } from "@/api/sso";
import { Button } from "@/components/ui/button";

/**
 * «Войти через корпоративный вход» (BIZ-53 разд. 53.3, срез-204).
 *
 * Кнопка появляется ТОЛЬКО когда у этой организации единый вход настроен.
 * Кнопка, которая всегда кончается отказом, хуже отсутствующей: человек нажмёт
 * её первой, получит ошибку и решит, что сломана платформа, — а чинить надо
 * настройку у его же администратора.
 *
 * Слаг организации человек вводит на том же экране, поэтому проверка идёт при
 * каждом его изменении. Ответ для чужой и несуществующей организации
 * одинаковый — «не настроено», иначе по этому экрану перебирали бы заказчиков.
 */

interface SsoButtonProps {
  tenantSlug: string;
}

export const SsoButton = ({ tenantSlug }: SsoButtonProps) => {
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const slug = tenantSlug.trim();
    if (!slug) {
      setEnabled(false);
      return;
    }
    let alive = true;
    ssoApi
      .status(slug)
      .then((data) => {
        if (alive) setEnabled(Boolean(data?.enabled));
      })
      .catch(() => {
        if (alive) setEnabled(false);
      });
    return () => {
      alive = false;
    };
  }, [tenantSlug]);

  if (!enabled) return null;

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await ssoApi.start(tenantSlug.trim());
      window.location.assign(data.authorization_url);
    } catch (caught) {
      // Причина приходит с сервера словами: «не настроен», «заполнено не
      // полностью», «секрет не выдан окружению» чинят разные люди.
      const message =
        (caught as { message?: string })?.message ??
        "Не удалось начать вход через SSO";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2" data-testid="sso-login">
      <Button
        type="button"
        variant="outline"
        className="w-full"
        disabled={busy}
        onClick={() => void start()}
      >
        {busy ? "Переход к провайдеру..." : "Войти через корпоративный вход"}
      </Button>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
};
