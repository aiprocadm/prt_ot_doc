import { apiClient } from "@/api/client";

export type SearchType = "documents" | "people" | "sites" | "incidents" | "inspections" | "files" | "ppe" | "risk" | "training" | "jobs" | "templates";

export interface SearchItem {
  kind: "entity" | "file";
  entity_type: string;
  entity_id: string;
  file_id?: string | null;
  title: string;
  subtitle?: string;
  tags?: Record<string, string>;
  status?: string;
  updated_at?: string;
  snippet?: string;
  score?: number;
  deeplink?: string;
}

export interface SearchResponse {
  q: string;
  total?: number;
  facets: {
    type_counts?: Record<string, number>;
    status_counts?: Record<string, number>;
    company_counts?: Record<string, number>;
    site_counts?: Record<string, number>;
    project_counts?: Record<string, number>;
    risk_level_counts?: Record<string, number>;
  };
  items: SearchItem[];
  next_cursor?: string | null;
  correlation_id?: string;
}

export interface SearchMemoryItem {
  id: string;
  q: string;
  types: string[];
  hit_count?: number;
  last_used_at?: string | null;
}

export interface SavedSearchItem extends SearchMemoryItem {
  name: string;
  filters?: Record<string, unknown>;
  is_shared?: boolean;
}

export const fetchSearch = async (params: {
  q?: string;
  types?: SearchType[];
  cursor?: string;
  limit?: number;
  status?: string;
  company_id?: string;
  site_id?: string;
  project_id?: string;
  contractor_id?: string;
  risk_level?: string;
  date_from?: string;
  date_to?: string;
  sort?: "relevance" | "updated_at" | "date";
}) => {
  const { data } = await apiClient.get<SearchResponse>("/search", {
    params: {
      ...params,
      types: params.types?.join(","),
    },
  });
  return data;
};

export const searchGlobal = async (q: string) => fetchSearch({ q, limit: 8 });

export const fetchRecentSearches = async () => {
  const { data } = await apiClient.get<{ items: SearchMemoryItem[] }>("/search/recent");
  return data.items;
};

export const fetchSavedSearches = async () => {
  const { data } = await apiClient.get<{ items: SavedSearchItem[] }>("/search/saved");
  return data.items;
};

export const createSavedSearch = async (payload: { name: string; q: string; types: string[]; filters?: Record<string, unknown>; is_shared?: boolean }) => {
  const { data } = await apiClient.post<SavedSearchItem>("/search/saved", payload);
  return data;
};

export const deleteSavedSearch = async (id: string) => {
  const { data } = await apiClient.delete<{ deleted: boolean }>(`/search/saved/${id}`);
  return data;
};

export const fetchArchiveFiles = async (params: {
  cursor?: string;
  limit?: number;
  status?: string;
  site_id?: string;
  project_id?: string;
  contractor_id?: string;
}) => {
  const { data } = await apiClient.get<{ items: Array<Record<string, unknown>>; next_cursor?: string | null }>("/archive/files", { params });
  return data;
};
