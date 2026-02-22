import { apiClient } from "@/api/client";

export type SearchType = "documents" | "people" | "sites" | "incidents" | "inspections" | "files";

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
}

export interface SearchResponse {
  q: string;
  facets: Record<string, number>;
  items: SearchItem[];
  next_cursor?: string | null;
}

export const fetchSearch = async (params: {
  q: string;
  types?: SearchType[];
  cursor?: string;
  limit?: number;
  status?: string;
  company_id?: string;
  site_id?: string;
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
