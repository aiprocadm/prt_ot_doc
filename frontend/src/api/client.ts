import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";
import { appConfig } from "@/config/env";
import { handleApiError } from "@/api/errorHandling";
import { tokenStorage } from "@/api/tokenStorage";
import { managedClientStorage } from "@/api/managedClientStorage";
import { tenantStorage } from "@/api/tenantStorage";
import type { ApiError, ApiFieldError } from "@/types/dto/common";
import type { RefreshResponseDto } from "@/types/dto/auth";

const API_BASE_URL = appConfig.apiBaseUrl;

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;
const subscribers: Array<(token: string | null) => void> = [];
const TENANT_WHITELIST = [/\/v1\/health(\/|$)/];

const combineUrl = (baseURL: string, url: string) => {
  if (!baseURL) return url;
  if (!url) return baseURL;
  return `${baseURL.replace(/\/+$/, "")}/${url.replace(/^\/+/, "")}`;
};

const resolveRequestPath = (url: string, baseURL?: string) => {
  const combined = combineUrl(baseURL ?? "", url);
  if (combined.startsWith("http://") || combined.startsWith("https://")) {
    try {
      return new URL(combined).pathname;
    } catch {
      return combined;
    }
  }
  if (combined.startsWith("/")) return combined;
  if (!combined) return "";
  return `/${combined}`;
};

const isTenantRequiredPath = (path: string) => {
  const isV1 = /\/v1(\/|$)/.test(path);
  if (!isV1) return false;
  return !TENANT_WHITELIST.some((pattern) => pattern.test(path));
};

/**
 * Запросы, которые ОБЯЗАНЫ уходить от личности аутсорсера, даже когда
 * специалист работает в контуре Dedicated-клиента (срез-225).
 *
 * Портфель клиентов и сам вход-выход из контекста живут в пространстве
 * аутсорсера: клиента с таким `id` в чужом контуре просто нет. Если пустить их
 * по ключу контура, специалист не сможет из этого контура ВЫЙТИ — а выход из
 * чужого контекста обязан работать всегда.
 *
 * Сессионные ручки (`/auth/login`, `/auth/refresh`, `/auth/logout`) — тоже:
 * сессию держит личность аутсорсера, у ключа контура обновления нет вовсе.
 */
const OUTSOURCER_IDENTITY_PATHS: RegExp[] = [
  /\/v1\/managed-clients(\/|$)/,
  /\/v1\/auth\/(login|refresh|logout)(\/|$)/,
];

const keepsOutsourcerIdentity = (path: string) =>
  OUTSOURCER_IDENTITY_PATHS.some((pattern) => pattern.test(path));

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

type RequestWithServerRetry = InternalAxiosRequestConfig & {
  _serverRetryCount?: number;
};

/**
 * Пометка «запрос ушёл по ключу контура клиента» (срез-225).
 *
 * Нужна ответу, а не запросу: по заголовку это уже не отличить — к моменту
 * ответа в хранилище может лежать что угодно, а решение «обновлять токен или
 * выходить из контекста» зависит от того, ЧЕЙ ключ был у ЭТОГО запроса.
 */
type RequestWithContour = InternalAxiosRequestConfig & {
  _viaClientContour?: boolean;
};

const markContourRequest = (config: InternalAxiosRequestConfig): void => {
  (config as RequestWithContour)._viaClientContour = true;
};

const wentViaContour = (config: InternalAxiosRequestConfig | undefined) =>
  Boolean((config as RequestWithContour | undefined)?._viaClientContour);

declare module "axios" {
  export interface AxiosRequestConfig {
    /** Best-effort запрос: ошибки не показываются пользователю глобальным тостом. */
    silentApiErrorToast?: boolean;
  }
}

const SERVER_RETRY_STATUSES = new Set([500, 502, 503, 504]);
const MAX_SERVER_RETRIES = 2;

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

const normalizeFieldErrors = (value: unknown): ApiFieldError[] => {
  if (!Array.isArray(value)) return [];
  const items: ApiFieldError[] = [];
  value.forEach((item) => {
    if (
      !isRecord(item) ||
      typeof item.field !== "string" ||
      typeof item.message !== "string"
    )
      return;
    items.push({
      field: item.field,
      message: item.message,
      code: typeof item.code === "string" ? item.code : undefined,
    });
  });
  return items;
};

const normalizeApiError = (
  payload: unknown,
  fallback: { status: number; message: string; details?: unknown },
): ApiError => {
  if (!isRecord(payload)) {
    return {
      status: fallback.status,
      message: fallback.message,
      details: fallback.details ?? payload,
      field_errors: [],
    };
  }

  const details =
    "details" in payload ? payload.details : (fallback.details ?? payload);
  return {
    status: fallback.status,
    code: typeof payload.code === "string" ? payload.code : undefined,
    type: typeof payload.type === "string" ? payload.type : undefined,
    message:
      typeof payload.message === "string" ? payload.message : fallback.message,
    details,
    field_errors: normalizeFieldErrors(payload.field_errors),
    correlation_id:
      typeof payload.correlation_id === "string"
        ? payload.correlation_id
        : undefined,
    timestamp:
      typeof payload.timestamp === "string" ? payload.timestamp : undefined,
  };
};

const notifySubscribers = (token: string | null) => {
  subscribers.splice(0, subscribers.length).forEach((cb) => {
    try {
      cb(token);
    } catch {
      // Продолжаем уведомлять остальных подписчиков даже при ошибке
    }
  });
};

const addSubscriber = (callback: (token: string | null) => void) => {
  subscribers.push(callback);
};

export const requestTokenRefresh = async (): Promise<RefreshResponseDto> => {
  const tenant = tenantStorage.getTenant();
  if (!tenant?.slug) {
    throw {
      status: 0,
      code: "TENANT_REQUIRED",
      type: "tenancy",
      message: "Выберите контур перед выполнением запроса.",
      details: { url: "/auth/refresh", path: "/auth/refresh" },
      field_errors: [],
    } satisfies ApiError;
  }

  const response = await axios.post<RefreshResponseDto>(
    `${API_BASE_URL}/auth/refresh`,
    {},
    {
      headers: { "X-Tenant": tenant.slug },
      withCredentials: true,
      timeout: 15_000,
    },
  );
  return response.data;
};

const refreshToken = async (): Promise<string | null> => {
  if (isRefreshing && refreshPromise) return refreshPromise;

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const response = await requestTokenRefresh();
      tokenStorage.setTokens({
        accessToken: response.access_token,
      });
      return response.access_token;
    } catch {
      tokenStorage.clear();
      return null;
    }
  })();

  // isRefreshing и refreshPromise сбрасываются ПОСЛЕ notifySubscribers,
  // чтобы новые 401-запросы не запустили параллельный refresh в микро-окне
  // между завершением IIFE и уведомлением ожидающих подписчиков.
  refreshPromise.finally(() => {
    notifySubscribers(tokenStorage.getAccessToken());
    isRefreshing = false;
    refreshPromise = null;
  });

  return refreshPromise;
};

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

tokenStorage.hydrate();
tenantStorage.hydrate();
managedClientStorage.hydrate();

apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  const tenant = tenantStorage.getTenant();
  config.headers = config.headers ?? {};
  const requestUrl = config.url ?? "";
  const requestPath = resolveRequestPath(
    requestUrl,
    config.baseURL ?? API_BASE_URL,
  );
  const requiresTenant = isTenantRequiredPath(requestPath);
  if (!tenant && requiresTenant) {
    const error = {
      status: 0,
      code: "TENANT_REQUIRED",
      type: "tenancy",
      message: "Выберите контур перед выполнением запроса.",
      details: { url: requestUrl, path: requestPath },
      field_errors: [],
    } satisfies ApiError;
    handleApiError(error, requestUrl);
    return Promise.reject(error);
  }
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (tenant && requiresTenant) {
    config.headers["X-Tenant"] = tenant.slug;
  }
  // BIZ-49 разд. 49.3: активный контекст клиента едет тем же путём, что и
  // арендатор — заголовком. Бэкенд проверит грант и запишет след в аудит;
  // если гранта нет, он ответит 403, а не сделает вид, что контекста не было.
  const clientContext = managedClientStorage.get();
  if (clientContext && requiresTenant) {
    config.headers["X-Managed-Client"] = clientContext.clientId;
  }
  // Срез-225. У Dedicated-клиента данные лежат в ЕГО арендаторе, и заголовком
  // туда не попасть: нужен ключ от контура, который выдаёт вход в контекст.
  // Подменяем ОБЕ вещи разом — токен и арендатора, — потому что порознь они
  // бессмысленны: свой токен в чужом контуре не примут, а чужой арендатор со
  // своим токеном — это ровно та попытка пролезть к соседу, которую сервер
  // обязан отвергнуть.
  const contour = requiresTenant ? managedClientStorage.contour() : null;
  if (contour && !keepsOutsourcerIdentity(requestPath)) {
    config.headers.Authorization = `Bearer ${contour.accessToken}`;
    config.headers["X-Tenant"] = contour.tenantSlug;
    // В своём контуре клиента специалист — обычный его пользователь: строки
    // «ведомый клиент» там нет, а метка делегирования уже лежит В ТОКЕНЕ, и
    // запреты разд. 63.2 действуют по ней (срез-215).
    delete config.headers["X-Managed-Client"];
    markContourRequest(config);
  }
  config.timeout = config.timeout ?? 15_000;
  return config;
});

const CONTEXT_EXPIRED_CODE = "MANAGED_CLIENT_CONTEXT_EXPIRED";

const isExpiredClientContext = (data: unknown): boolean => {
  if (!data || typeof data !== "object") return false;
  const body = data as Record<string, unknown>;
  const detail = body.detail as Record<string, unknown> | undefined;
  return (
    body.code === CONTEXT_EXPIRED_CODE || detail?.code === CONTEXT_EXPIRED_CODE
  );
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config;
    const status = error.response?.status ?? 0;
    // BIZ-49 срез-10: сервер сказал, что работа «от имени клиента» истекла.
    // Держать локальный контекст после этого нельзя: интерфейс продолжил бы
    // показывать баннер «вы работаете от имени X», хотя каждый следующий
    // запрос получает отказ — а данные при этом уже НЕ отфильтрованы.
    if (status === 403 && isExpiredClientContext(error.response?.data)) {
      managedClientStorage.clear();
    }
    // Срез-225. Ключ от контура клиента ОБНОВЛЕНИЮ НЕ ПОДЛЕЖИТ — так решено на
    // сервере (срез-215): обновление пережило бы и срок контекста, и отзыв
    // согласия. Отправить сюда обычный `/auth/refresh` было бы хуже, чем
    // бесполезно: он вернул бы токен ЛИЧНОСТИ АУТСОРСЕРА, запрос повторился бы
    // с ним в контуре клиента — и специалист продолжил бы работать «в контуре»
    // под своим настоящим именем. Поэтому ключ погас — значит, вышли из
    // контекста, а человек войдёт заново, и вход перепроверит основание.
    if (status === 401 && wentViaContour(originalRequest)) {
      managedClientStorage.clear();
      const apiError = normalizeApiError(error.response?.data, {
        status,
        message: "Доступ к контуру клиента закончился. Войдите в контекст заново.",
        details: error.response?.data,
      });
      handleApiError(apiError, originalRequest?.url);
      return Promise.reject(apiError);
    }
    if (status === 401 && originalRequest && !originalRequest._retry) {
      const requestAuthHeader = originalRequest.headers?.Authorization;
      const hasAccessToken = Boolean(
        (typeof requestAuthHeader === "string" && requestAuthHeader.trim()) ||
          tokenStorage.getAccessToken(),
      );
      if (!hasAccessToken) {
        // No token present: do not storm /auth/refresh, but keep unified auth handling.
        const apiError = normalizeApiError(error.response?.data, {
          status,
          message: error.message ?? "Unauthorized",
          details: error.response?.data,
        });
        handleApiError(apiError, originalRequest?.url);
        return Promise.reject(apiError);
      } else {
        originalRequest._retry = true;

        if (isRefreshing) {
          return new Promise((resolve, reject) => {
            addSubscriber((token) => {
              if (token && originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${token}`;
                resolve(apiClient(originalRequest));
              } else {
                // Refresh failed: reject with a normalized ApiError (and run unified
                // handling) so queued 401s surface like every other error path, not as
                // a raw AxiosError missing .status/.field_errors.
                const apiError = normalizeApiError(error.response?.data, {
                  status,
                  message: error.message ?? "Unauthorized",
                  details: error.response?.data,
                });
                handleApiError(apiError, originalRequest?.url);
                reject(apiError);
              }
            });
          });
        }

        const newToken = await refreshToken();
        if (newToken && originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return apiClient(originalRequest);
        }
        const apiError = normalizeApiError(error.response?.data, {
          status,
          message: error.message ?? "Unauthorized",
          details: error.response?.data,
        });
        handleApiError(apiError, originalRequest?.url);
        return Promise.reject(apiError);
      }
    }

    if (originalRequest) {
      const method = (originalRequest.method ?? "get").toLowerCase();
      const cfg = originalRequest as RequestWithServerRetry;
      const attempt = cfg._serverRetryCount ?? 0;
      if (
        method === "get" &&
        SERVER_RETRY_STATUSES.has(status) &&
        attempt < MAX_SERVER_RETRIES
      ) {
        cfg._serverRetryCount = attempt + 1;
        const backoff = 400 * 2 ** attempt + Math.floor(Math.random() * 250);
        await sleep(backoff);
        return apiClient(originalRequest);
      }
    }

    const apiError = normalizeApiError(error.response?.data, {
      status,
      message: error.message ?? "Unexpected error",
      details: error.response?.data,
    });

    if (!originalRequest?.silentApiErrorToast) {
      handleApiError(apiError, originalRequest?.url);
    }
    return Promise.reject(apiError);
  },
);
