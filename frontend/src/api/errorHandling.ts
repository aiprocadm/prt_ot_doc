import { toast } from "sonner";

import type { ApiError } from "@/types/dto/common";
import { tokenStorage } from "@/api/tokenStorage";
import { setReturnTo } from "@/utils/returnTo";

const AUTH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout"];

const isAuthPath = (url?: string) => {
  if (!url) return false;
  return AUTH_PATHS.some((path) => url.includes(path));
};

const redirectToLogin = () => {
  if (typeof window === "undefined") return;
  const current = `${window.location.pathname}${window.location.search}`;
  if (!window.location.pathname.startsWith("/auth")) {
    setReturnTo(current);
  }
  window.location.assign("/auth/login");
};

export const handleApiError = (error: ApiError, requestUrl?: string) => {
  const status = error.status ?? 0;

  if (error.code === "TENANT_REQUIRED") {
    toast.error("Выберите контур или организацию перед загрузкой данных.");
    return;
  }

  if (error.code === "BILLING_BLOCKED") {
    toast.error("Доступ ограничен из-за статуса оплаты. Откройте раздел Администрирование → Биллинг.");
    return;
  }

  if (error.code === "QUOTA_EXCEEDED") {
    toast.error("Превышен лимит тарифа. Проверьте usage и лимиты в разделе Биллинг.");
    return;
  }

  if (error.code === "FEATURE_DISABLED") {
    toast.error("Функция недоступна на текущем тарифе.");
    return;
  }

  if (status === 401 && !isAuthPath(requestUrl)) {
    tokenStorage.clear();
    redirectToLogin();
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
    toast.error("Проверьте введённые данные и повторите попытку.");
    return;
  }

  if (status >= 500) {
    toast.error("Сервис временно недоступен. Попробуйте позже.");
  }
};
