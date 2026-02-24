import { createWithEqualityFn } from "zustand/traditional";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { tokenStorage } from "@/api/tokenStorage";
import { tenantStorage } from "@/api/tenantStorage";
import { resetTenantStores } from "@/stores/reset";
import type { ApiError } from "@/types/dto/common";
import type { LoginRequestDto, LoginResponseDto, PermissionsResponseDto, RefreshResponseDto, UserDto } from "@/types/dto/auth";

interface AuthState {
  user: UserDto | null;
  loading: boolean;
  error: ApiError | null;
  isAuthenticated: boolean;
  initialized: boolean;
  login: (payload: LoginRequestDto) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  initialize: () => Promise<void>;
}

const persistTokens = (payload: { access_token: string; refresh_token: string; expires_in: number }) => {
  tokenStorage.setTokens({
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    expiresIn: payload.expires_in
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
export const useAuthStore = createWithEqualityFn<AuthState>()(
  immer((set, get) => ({
    user: null,
    loading: false,
    error: null,
    isAuthenticated: false,
    initialized: false,
    initialize: async () => {
      tokenStorage.hydrate();
      const refreshToken = tokenStorage.getRefreshToken();
      if (!refreshToken) {
        set((state) => {
          state.isAuthenticated = false;
          state.user = null;
          state.error = null;
          state.initialized = true;
        });
        return;
      }
      try {
        const { data } = await apiClient.post<RefreshResponseDto>("/auth/refresh", { refresh_token: refreshToken });
        persistTokens(data);
        let profile: UserDto | null = null;
        let profileError: ApiError | null = null;
        try {
          const { data: profileResponse } = await apiClient.get<UserDto>("/auth/me");
          profile = await hydratePermissions(profileResponse);
        } catch (error) {
          profileError = (error as ApiError) ?? null;
        }
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
          state.error = (error as ApiError) ?? null;
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
        const { data } = await apiClient.post<LoginResponseDto>("/auth/login", payload);
        persistTokens(data);
        const enrichedUser = await hydratePermissions(data.user);
        set((state) => {
          state.user = enrichedUser;
          state.isAuthenticated = true;
          state.initialized = true;
        });
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
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
      const refreshToken = tokenStorage.getRefreshToken();
      if (!refreshToken) return;
      const { data } = await apiClient.post<RefreshResponseDto>("/auth/refresh", { refresh_token: refreshToken });
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
            state.error = (error as ApiError) ?? null;
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
