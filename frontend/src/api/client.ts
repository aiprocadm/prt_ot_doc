import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import { appConfig } from "@/config/env";
import { handleApiError } from "@/api/errorHandling";
import { tokenStorage } from "@/api/tokenStorage";
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

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

type RequestWithServerRetry = InternalAxiosRequestConfig & { _serverRetryCount?: number };

const SERVER_RETRY_STATUSES = new Set([500, 502, 503, 504]);
const MAX_SERVER_RETRIES = 2;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const normalizeFieldErrors = (value: unknown): ApiFieldError[] => {
  if (!Array.isArray(value)) return [];
  const items: ApiFieldError[] = [];
  value.forEach((item) => {
    if (!isRecord(item) || typeof item.field !== "string" || typeof item.message !== "string") return;
    items.push({
      field: item.field,
      message: item.message,
      code: typeof item.code === "string" ? item.code : undefined
    });
  });
  return items;
};

const normalizeApiError = (payload: unknown, fallback: { status: number; message: string; details?: unknown }): ApiError => {
  if (!isRecord(payload)) {
    return {
      status: fallback.status,
      message: fallback.message,
      details: fallback.details ?? payload,
      field_errors: []
    };
  }

  const details = "details" in payload ? payload.details : fallback.details ?? payload;
  return {
    status: fallback.status,
    code: typeof payload.code === "string" ? payload.code : undefined,
    type: typeof payload.type === "string" ? payload.type : undefined,
    message: typeof payload.message === "string" ? payload.message : fallback.message,
    details,
    field_errors: normalizeFieldErrors(payload.field_errors),
    correlation_id: typeof payload.correlation_id === "string" ? payload.correlation_id : undefined,
    timestamp: typeof payload.timestamp === "string" ? payload.timestamp : undefined
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
      field_errors: []
    } satisfies ApiError;
  }

  const response = await axios.post<RefreshResponseDto>(
    `${API_BASE_URL}/auth/refresh`,
    {},
    {
      headers: { "X-Tenant": tenant.slug },
      withCredentials: true,
      timeout: 15_000
    }
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
        accessToken: response.access_token
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
  withCredentials: true
});

tokenStorage.hydrate();
tenantStorage.hydrate();

apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken();
  const tenant = tenantStorage.getTenant();
  config.headers = config.headers ?? {};
  const requestUrl = config.url ?? "";
  const requestPath = resolveRequestPath(requestUrl, config.baseURL ?? API_BASE_URL);
  const requiresTenant = isTenantRequiredPath(requestPath);
  if (!tenant && requiresTenant) {
    const error = {
      status: 0,
      code: "TENANT_REQUIRED",
      type: "tenancy",
      message: "Выберите контур перед выполнением запроса.",
      details: { url: requestUrl, path: requestPath },
      field_errors: []
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
  config.timeout = config.timeout ?? 15_000;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config;
    const status = error.response?.status ?? 0;
    if (status === 401 && originalRequest && !originalRequest._retry) {
      const requestAuthHeader = originalRequest.headers?.Authorization;
      const hasAccessToken = Boolean(
        (typeof requestAuthHeader === "string" && requestAuthHeader.trim()) || tokenStorage.getAccessToken()
      );
      if (!hasAccessToken) {
        // No token present: do not storm /auth/refresh, but keep unified auth handling.
        const apiError = normalizeApiError(error.response?.data, {
          status,
          message: error.message ?? "Unauthorized",
          details: error.response?.data
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
                  details: error.response?.data
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
          details: error.response?.data
        });
        handleApiError(apiError, originalRequest?.url);
        return Promise.reject(apiError);
      }
    }

    if (originalRequest) {
      const method = (originalRequest.method ?? "get").toLowerCase();
      const cfg = originalRequest as RequestWithServerRetry;
      const attempt = cfg._serverRetryCount ?? 0;
      if (method === "get" && SERVER_RETRY_STATUSES.has(status) && attempt < MAX_SERVER_RETRIES) {
        cfg._serverRetryCount = attempt + 1;
        const backoff = 400 * 2 ** attempt + Math.floor(Math.random() * 250);
        await sleep(backoff);
        return apiClient(originalRequest);
      }
    }

    const apiError = normalizeApiError(error.response?.data, {
      status,
      message: error.message ?? "Unexpected error",
      details: error.response?.data
    });

    handleApiError(apiError, originalRequest?.url);
    return Promise.reject(apiError);
  }
);

export const setAuthHeader = (token: string | null) => {
  if (!token) return;
  apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
};
