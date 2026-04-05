import { toast } from "sonner";

import type { ApiError } from "@/types/dto/common";
import { tokenStorage } from "@/api/tokenStorage";
import { requestAuthRedirect } from "@/router/authRedirect";
import { sessionStorageSetItem } from "@/utils/browserStorage";

const AUTH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout"];

const BILLING_ALERT_STORAGE_KEY = "billing:alert";

const rememberBillingAlert = (code: string) => {
  sessionStorageSetItem(BILLING_ALERT_STORAGE_KEY, JSON.stringify({ code, ts: Date.now() }));
};

export { BILLING_ALERT_STORAGE_KEY };

const isAuthPath = (url?: string) => {
  if (!url) return false;
  return AUTH_PATHS.some((path) => url.includes(path));
};

export const handleApiError = (error: ApiError, requestUrl?: string) => {
  const status = error.status ?? 0;

  if (error.code === "TENANT_REQUIRED") {
    toast.error("Выберите контур или организацию перед загрузкой данных.");
    return;
  }

  if (error.code === "BILLING_BLOCKED" || error.code === "TENANT_SUSPENDED" || error.code === "TENANT_PAST_DUE") {
    rememberBillingAlert(error.code);
    toast.error("Доступ ограничен из-за статуса оплаты. Откройте раздел Администрирование → Биллинг.");
    return;
  }

  if (error.code === "QUOTA_EXCEEDED") {
    rememberBillingAlert("QUOTA_EXCEEDED");
    toast.error("Превышен лимит тарифа. Проверьте usage и лимиты в разделе Биллинг.");
    return;
  }

  if (error.code === "FEATURE_DISABLED") {
    toast.error("Функция недоступна на текущем тарифе.");
    return;
  }

  if (status === 401 && !isAuthPath(requestUrl)) {
    tokenStorage.clear();
    requestAuthRedirect("unauthorized");
    return;
  }

  if (status === 403) {
    toast.error("Недостаточно прав для выполнения операции.");
    return;
  }

  if (status === 404) {
    toast.error("Запрошенный ресурс недоступен.");
    return;
  }

  if (status === 409) {
    toast.error("Конфликт данных. Обновите страницу и попробуйте снова.");
    return;
  }

  if (status === 422) {
    const fe = error.field_errors?.filter((f) => f.field && f.message) ?? [];
    const detail = fe.length > 0 ? fe.map((f) => `${f.field}: ${f.message}`).join(". ") : null;
    toast.error(detail ?? "Проверьте введённые данные и повторите попытку.");
    return;
  }

  // 5xx: не дублируем тост — на экранах с ErrorState сообщение уже в блоке; иначе шум.
  if (status >= 500) {
    return;
  }
};
