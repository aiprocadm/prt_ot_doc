import axios, { type AxiosError, type AxiosInstance } from "axios";
import { appConfig } from "@/config/env";
import { handleApiError } from "@/api/errorHandling";
import { tokenStorage } from "@/api/tokenStorage";
import { tenantStorage } from "@/api/tenantStorage";
import type { ApiError } from "@/types/dto/common";
import type { RefreshResponseDto } from "@/types/dto/auth";

const API_BASE_URL = appConfig.apiBaseUrl;

let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;
const subscribers: Array<(token: string | null) => void> = [];

const notifySubscribers = (token: string | null) => {
  subscribers.splice(0, subscribers.length).forEach((cb) => cb(token));
};

const addSubscriber = (callback: (token: string | null) => void) => {
  subscribers.push(callback);
};

const refreshToken = async (): Promise<string | null> => {
  if (isRefreshing && refreshPromise) return refreshPromise;

  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const refreshTokenValue = tokenStorage.getRefreshToken();
      if (!refreshTokenValue) return null;
      const response = await axios.post<RefreshResponseDto>(`${API_BASE_URL}/auth/refresh`, {
        refresh_token: refreshTokenValue
      });
      tokenStorage.setTokens({
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token,
        expiresIn: response.data.expires_in
      });
      return response.data.access_token;
    } catch (error) {
      tokenStorage.clear();
      return null;
    } finally {
      isRefreshing = false;
    }
  })();

  refreshPromise.finally(() => {
    notifySubscribers(tokenStorage.getAccessToken());
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
  const requiresTenant = !requestUrl.includes("/auth/");
  if (!tenant && requiresTenant) {
    return Promise.reject({
      status: 0,
      code: "TENANT_REQUIRED",
      message: "Выберите контур перед выполнением запроса.",
      details: { url: requestUrl }
    } satisfies ApiError);
  }
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (tenant) {
    config.headers["X-Tenant"] = tenant.slug;
    if (tenant.site) {
      config.headers["X-Site"] = tenant.site;
    }
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
      originalRequest._retry = true;

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          addSubscriber((token) => {
            if (token && originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(apiClient(originalRequest));
            } else {
              reject(error);
            }
          });
        });
      }

      const newToken = await refreshToken();
      if (newToken && originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      }
    }

    const apiError: ApiError = {
      status,
      code: (error.response?.data as { code?: string })?.code,
      message:
        (error.response?.data as { message?: string })?.message ??
        error.message ??
        "Unexpected error",
      details: error.response?.data
    };

    handleApiError(apiError, originalRequest?.url);
    return Promise.reject(apiError);
  }
);

export const setAuthHeader = (token: string | null) => {
  if (!token) return;
  apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
};
