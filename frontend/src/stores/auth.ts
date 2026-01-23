import { createWithEqualityFn } from "zustand/traditional";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { tokenStorage } from "@/api/tokenStorage";
import type { ApiError } from "@/types/dto/common";
import type { LoginRequestDto, LoginResponseDto, RefreshResponseDto, UserDto } from "@/types/dto/auth";

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
          profile = profileResponse;
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
        set((state) => {
          state.user = data.user;
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
          set((state) => {
            state.user = profile;
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
      set((state) => {
        state.user = null;
        state.isAuthenticated = false;
        state.initialized = true;
        state.error = null;
      });
    }
  }))
);
