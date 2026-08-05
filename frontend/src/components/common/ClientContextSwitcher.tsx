import { useCallback, useEffect, useState } from "react";

import { managedClientsApi, type MyManagedClient } from "@/api/managedClients";
import { managedClientStorage, type StoredClientContext } from "@/api/managedClientStorage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/common/ErrorState";
import type { ApiError } from "@/types/dto/common";

/**
 * BIZ-49 разд. 49.3: «Специалист аутсорсера должен переключаться между
 * клиентами БЕЗ ПЕРЕЛОГИНА».
 *
 * Две вещи здесь не украшения, а требования безопасности:
 *
 * 1. **Индикатор постоянный и заметный.** Контекст переживает перезагрузку
 *    страницы, поэтому спрятать его в выпадающем списке нельзя: человек забудет,
 *    от чьего имени работает, и внесёт данные не тому клиенту.
 * 2. **Выход — в один клик и всегда на виду.** Если выйти сложнее, чем войти,
 *    в контексте будут сидеть «на всякий случай».
 */

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

const formatLeft = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m} мин` : `${s} сек`;
};

const selectClass =
  "flex h-9 rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

interface ClientContextSwitcherProps {
  /** Вызывается после смены контекста — чтобы страница перечитала данные. */
  onContextChange?: (context: StoredClientContext | null) => void;
}

export const ClientContextSwitcher = ({ onContextChange }: ClientContextSwitcherProps) => {
  const [clients, setClients] = useState<MyManagedClient[]>([]);
  const [sections, setSections] = useState<string[]>([]);
  const [active, setActive] = useState<StoredClientContext | null>(() => {
    // Вкладка могла пролежать всю ночь: показывать «вы работаете от имени»
    // по протухшему состоянию нельзя — сервер такой контекст уже не признаёт.
    const stored = managedClientStorage.get();
    if (managedClientStorage.isExpired(stored)) {
      managedClientStorage.clear();
      return null;
    }
    return stored;
  });
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [expired, setExpired] = useState(false);

  const load = useCallback(async () => {
    try {
      const mine = await managedClientsApi.my();
      setClients(mine.items);
      setSections(mine.scopedSections);
      setError(null);
    } catch {
      // Модуль может быть не подключён — это не ошибка пользователя,
      // переключателю просто нечего показывать.
      setClients([]);
      setSections([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const enter = async (clientId: string) => {
    if (!clientId) return;
    setBusy(true);
    setError(null);
    try {
      // Вход подтверждает бэкенд: он проверяет грант и ПИШЕТ СЛЕД В АУДИТ.
      // Записывать контекст локально до подтверждения нельзя — иначе интерфейс
      // покажет работу «от имени клиента», которой на сервере не случилось.
      const confirmed = await managedClientsApi.enterContext(clientId);
      const next = {
        clientId: confirmed.client_id,
        clientName: confirmed.client_name,
        expiresAt: confirmed.expires_at ?? undefined
      };
      managedClientStorage.set(next);
      setActive(next);
      onContextChange?.(next);
    } catch (err) {
      setError(asApiError(err, "Не удалось войти в контекст клиента"));
    } finally {
      setBusy(false);
    }
  };

  const leave = useCallback(
    async (expired = false) => {
      // Сначала гасим локально: если сеть отвалилась, специалист всё равно
      // обязан выйти из чужого контекста, а не остаться в нём с ошибкой.
      managedClientStorage.clear();
      setActive(null);
      setExpired(expired);
      onContextChange?.(null);
      try {
        await managedClientsApi.leaveContext();
      } catch {
        // Сервер закроет сессию сам по сроку — молчим, чтобы выход из
        // контекста не выглядел неудавшимся.
      }
    },
    [onContextChange]
  );

  // Срок работы «от имени» истекает и БЕЗ участия пользователя: вкладка может
  // просто лежать открытой. Пока баннер висит, счётчик обязан идти сам.
  useEffect(() => {
    if (!active?.expiresAt) return;
    const tick = () => {
      if (managedClientStorage.isExpired(active)) {
        void leave(true);
        return;
      }
      setSecondsLeft(Math.max(0, Math.round((Date.parse(active.expiresAt!) - Date.now()) / 1000)));
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [active, leave]);

  if (active) {
    return (
      <div
        className="flex flex-wrap items-center gap-2 rounded-md border border-amber-400 bg-amber-50 px-3 py-2 dark:bg-amber-950"
        data-testid="client-context-banner"
        role="status"
      >
        <Badge variant="destructive">Контекст клиента</Badge>
        <span className="text-sm">
          Вы работаете от имени: <strong>{active.clientName}</strong>
        </span>
        <span className="text-xs text-muted-foreground">Действия фиксируются в аудите</span>
        {secondsLeft !== null && (
          <span className="text-xs font-medium" data-testid="client-context-countdown">
            Осталось {formatLeft(secondsLeft)}
          </span>
        )}
        {/* Фильтр применён пока не во всех разделах, и молчать об этом нельзя:
            специалист поверит вывеске и внесёт данные не тому клиенту. */}
        {sections.length > 0 && (
          <span className="text-xs text-muted-foreground" data-testid="client-context-sections">
            Данные клиента показываются в разделах: {sections.join(", ")}. В остальных — данные
            всех клиентов.
          </span>
        )}
        <Button type="button" size="sm" variant="outline" onClick={() => void leave()}>
          Выйти из контекста
        </Button>
      </div>
    );
  }

  if (clients.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="client-context-switcher">
      {expired && (
        <span className="text-xs text-amber-700" data-testid="client-context-expired">
          Время работы от имени клиента вышло — войдите заново, если работа продолжается.
        </span>
      )}
      <label className="text-xs text-muted-foreground" htmlFor="client-context-select">
        Работать от имени клиента
      </label>
      <select
        id="client-context-select"
        className={selectClass}
        defaultValue=""
        disabled={busy}
        onChange={(e) => void enter(e.target.value)}
      >
        <option value="">— не выбрано —</option>
        {clients.map((c) => (
          <option key={c.client_id} value={c.client_id}>
            {c.client_name}
          </option>
        ))}
      </select>
      <ErrorState error={error ?? undefined} />
    </div>
  );
};
