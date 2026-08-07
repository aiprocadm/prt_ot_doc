import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { SearchType } from "@/api/search";
import { searchTabs, type SearchTab } from "./types";

const asSearchTypeList = (tab: SearchTab): SearchType[] => [tab as SearchType];

export const useSearchUrlState = () => {
  const [params, setParams] = useSearchParams();

  const q = params.get("q") ?? "";
  const type = (params.get("type") as SearchTab | null) ?? "documents";
  const status = params.get("status") ?? "";
  const companyId = params.get("company_id") ?? "";
  const siteId = params.get("site_id") ?? "";
  const projectId = params.get("project_id") ?? "";
  const riskLevel = params.get("risk_level") ?? "";

  const patchParams = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([key, value]) => {
      if (value && value.trim()) next.set(key, value);
      else next.delete(key);
    });
    setParams(next);
  };

  const replaceWithSavedSearch = (item: {
    q: string;
    types: string[];
    filters?: Record<string, unknown>;
  }) => {
    const next = new URLSearchParams();
    next.set("q", item.q);
    if (item.types[0]) next.set("type", item.types[0]);
    const filters = item.filters ?? {};
    if (typeof filters.status === "string") next.set("status", filters.status);
    if (typeof filters.company_id === "string")
      next.set("company_id", filters.company_id);
    if (typeof filters.site_id === "string")
      next.set("site_id", filters.site_id);
    if (typeof filters.project_id === "string")
      next.set("project_id", filters.project_id);
    if (typeof filters.risk_level === "string")
      next.set("risk_level", filters.risk_level);
    setParams(next);
  };

  const activeTypes = useMemo(() => asSearchTypeList(type), [type]);
  const activeFilterCount = useMemo(
    () =>
      [status, companyId, siteId, projectId, riskLevel].filter(Boolean).length,
    [status, companyId, siteId, projectId, riskLevel],
  );

  return {
    params,
    setParams,
    q,
    type,
    status,
    companyId,
    siteId,
    projectId,
    riskLevel,
    activeTypes,
    activeFilterCount,
    patchParams,
    replaceWithSavedSearch,
    tabs: searchTabs,
  };
};
