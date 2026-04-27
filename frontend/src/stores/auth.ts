import { createWithEqualityFn } from "zustand/traditional";
import { immer } from "zustand/middleware/immer";
import { apiClient, requestTokenRefresh } from "@/api/client";
import { tokenStorage } from "@/api/tokenStorage";
import { tenantStorage } from "@/api/tenantStorage";
import { resetTenantStores } from "@/stores/reset";
import { useTenantStore } from "@/stores/tenant";
import { isApiError } from "@/utils/apiFormErrors";
import type { ApiError } from "@/types/dto/common";
import type { LoginRequestDto, LoginResponseDto, PermissionsResponseDto, UserDto } from "@/types/dto/auth";

const normalizeError = (error: unknown): ApiError =>
  isApiError(error)
    ? error
    : { status: 0, message: String((error as Error)?.message ?? "Unknown error"), field_errors: [] };

type LoginActionPayload = LoginRequestDto & {
  tenant: string;
};

interface AuthState {
  user: UserDto | null;
  loading: boolean;
  error: ApiError | null;
  isAuthenticated: boolean;
  initialized: boolean;
  login: (payload: LoginActionPayload) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  initialize: () => Promise<void>;
}

const persistTokens = (payload: { access_token: string }) => {
  tokenStorage.setTokens({
    accessToken: payload.access_token
  });
};



const hydratePermissions = async (user: UserDto | null): Promise<UserDto | null> => {
  if (!user) return user;
  try {
    const { data } = await apiClient.get<PermissionsResponseDto>("/auth/me/permissions");
    return {
      ...user,
      roles: data.roles?.length ? data.roles : user.roles,
      permissions: data.permissions,
      attributes: {
        ...(user.attributes ?? {}),
        company_ids: data.abac_scopes?.company_ids ?? user.attributes?.company_ids,
        site_ids: data.abac_scopes?.site_ids ?? user.attributes?.site_ids,
        project_ids: data.abac_scopes?.project_ids ?? user.attributes?.project_ids,
        contractor_ids: data.abac_scopes?.contractor_ids ?? user.attributes?.contractor_ids,
        risk_level_max: data.abac_scopes?.risk_level_max ?? user.attributes?.risk_level_max
      }
    };
  } catch {
    return user;
  }
};

const loadProfileWithPermissions = async (): Promise<{ profile: UserDto | null; profileError: ApiError | null }> => {
  let profile: UserDto | null = null;
  let profileError: ApiError | null = null;
  try {
    const { data: profileResponse } = await apiClient.get<UserDto>("/auth/me");
    profile = await hydratePermissions(profileResponse);
  } catch (error) {
    profileError = normalizeError(error);
  }
  return { profile, profileError };
};
export const useAuthStore = createWithEqualityFn<AuthState>()(
  immer((set, get) => ({
    user: null,
    loading: false,
    error: null,
    isAuthenticated: false,
    initialized: false,
    initialize: async () => {
      tokenStorage.hydrate();
      tenantStorage.hydrate();
      try {
        const data = await requestTokenRefresh();
        persistTokens(data);
        const { profile, profileError } = await loadProfileWithPermissions();
        set((state) => {
          state.user = profile;
          state.isAuthenticated = true;
          state.error = profileError;
          state.initialized = true;
        });
      } catch (error) {
        tokenStorage.clear();
        set((state) => {
          state.isAuthenticated = false;
          state.user = null;
          state.error = normalizeError(error);
          state.initialized = true;
        });
      }
    },
    login: async (payload) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const tenantSlug = payload.tenant.trim();
        useTenantStore.getState().setTenant({ slug: tenantSlug, name: tenantSlug });
        const { data } = await apiClient.post<LoginResponseDto>("/auth/login", {
          email: payload.email,
          password: payload.password
        });
        persistTokens(data);
        const { profile, profileError } = await loadProfileWithPermissions();
        set((state) => {
          state.user = profile;
          state.isAuthenticated = true;
          state.error = profileError;
          state.initialized = true;
        });
      } catch (error) {
        set((state) => {
          state.error = normalizeError(error);
          state.isAuthenticated = false;
          state.initialized = true;
        });
        throw error;
      } finally {
        set((state) => {
          state.loading = false;
        });
      }
    },
    refresh: async () => {
      const data = await requestTokenRefresh();
      persistTokens(data);
      set((state) => {
        state.isAuthenticated = true;
        state.initialized = true;
        state.error = null;
      });
      if (!get().user) {
        try {
          const { data: profile } = await apiClient.get<UserDto>("/auth/me");
          const enriched = await hydratePermissions(profile);
          set((state) => {
            state.user = enriched;
          });
        } catch (error) {
          set((state) => {
            state.error = normalizeError(error);
          });
        }
      }
    },
    logout: async () => {
      await apiClient.post("/auth/logout").catch(() => undefined);
      tokenStorage.clear();
      tenantStorage.clear();
      resetTenantStores();
      set((state) => {
        state.user = null;
        state.isAuthenticated = false;
        state.initialized = true;
        state.error = null;
      });
    }
  }))
);
