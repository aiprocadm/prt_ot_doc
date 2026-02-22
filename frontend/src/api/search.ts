import { apiClient } from "@/api/client";

export interface SearchItem {
  type: string;
  id: string;
  title: string;
  snippet?: string;
}

export const searchGlobal = async (q: string) => {
  const { data } = await apiClient.get<{ q: string; items: SearchItem[] }>("/search", { params: { q } });
  return data;
};
