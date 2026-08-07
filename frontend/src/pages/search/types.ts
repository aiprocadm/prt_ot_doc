import type { SearchType } from "@/api/search";

export type SearchTab = SearchType | "tasks" | "npa" | "contracts" | "orders";

export type SearchFacets = {
  type_counts?: Record<string, number>;
  status_counts?: Record<string, number>;
  company_counts?: Record<string, number>;
  site_counts?: Record<string, number>;
  project_counts?: Record<string, number>;
  risk_level_counts?: Record<string, number>;
};

export const searchTabs: SearchTab[] = [
  "documents",
  "files",
  "people",
  "sites",
  "incidents",
  "inspections",
  "risk",
  "ppe",
  "training",
  "jobs",
  "templates",
  "tasks",
  "npa",
  "contracts",
  "orders",
];
