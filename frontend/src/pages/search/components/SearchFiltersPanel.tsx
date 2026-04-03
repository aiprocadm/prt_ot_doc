import { Filter } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { SearchFacets } from "../types";

type Props = {
  facets: SearchFacets;
  status: string;
  companyId: string;
  siteId: string;
  projectId: string;
  riskLevel: string;
  onPatch: (patch: Record<string, string | undefined>) => void;
};

export const SearchFiltersPanel = ({ facets, status, companyId, siteId, projectId, riskLevel, onPatch }: Props) => (
  <Card>
    <CardHeader className="flex flex-row items-center justify-between">
      <CardTitle className="flex items-center gap-2 text-base">
        <Filter className="h-4 w-4" /> Faceted filters
      </CardTitle>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onPatch({ status: undefined, company_id: undefined, site_id: undefined, project_id: undefined, risk_level: undefined })}
      >
        Сбросить
      </Button>
    </CardHeader>
    <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <div className="space-y-2">
        <label className="text-xs font-medium uppercase text-muted-foreground">Status</label>
        <select className="h-10 rounded-md border px-3" value={status} onChange={(event) => onPatch({ status: event.target.value || undefined })}>
          <option value="">Все</option>
          {Object.entries(facets.status_counts ?? {}).map(([key, value]) => (
            <option key={key} value={key}>
              {key} ({value})
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <label className="text-xs font-medium uppercase text-muted-foreground">Company scope</label>
        <Input placeholder="company_id" value={companyId} onChange={(event) => onPatch({ company_id: event.target.value || undefined })} />
        <div className="text-xs text-muted-foreground">Facet IDs: {Object.keys(facets.company_counts ?? {}).slice(0, 5).join(", ") || "—"}</div>
      </div>
      <div className="space-y-2">
        <label className="text-xs font-medium uppercase text-muted-foreground">Site scope</label>
        <Input placeholder="site_id" value={siteId} onChange={(event) => onPatch({ site_id: event.target.value || undefined })} />
        <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
          {Object.entries(facets.site_counts ?? {})
            .slice(0, 5)
            .map(([key, value]) => (
              <button type="button" key={key} className="rounded-full border px-2 py-0.5" onClick={() => onPatch({ site_id: key })}>
                {key} ({value})
              </button>
            ))}
        </div>
      </div>
      <div className="space-y-2">
        <label className="text-xs font-medium uppercase text-muted-foreground">Project scope</label>
        <Input placeholder="project_id" value={projectId} onChange={(event) => onPatch({ project_id: event.target.value || undefined })} />
        <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
          {Object.entries(facets.project_counts ?? {})
            .slice(0, 5)
            .map(([key, value]) => (
              <button type="button" key={key} className="rounded-full border px-2 py-0.5" onClick={() => onPatch({ project_id: key })}>
                {key} ({value})
              </button>
            ))}
        </div>
      </div>
      <div className="space-y-2">
        <label className="text-xs font-medium uppercase text-muted-foreground">Risk level</label>
        <Input placeholder="risk_level" value={riskLevel} onChange={(event) => onPatch({ risk_level: event.target.value || undefined })} />
        <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
          {Object.entries(facets.risk_level_counts ?? {})
            .slice(0, 5)
            .map(([key, value]) => (
              <button type="button" key={key} className="rounded-full border px-2 py-0.5" onClick={() => onPatch({ risk_level: key })}>
                {key} ({value})
              </button>
            ))}
        </div>
      </div>
    </CardContent>
  </Card>
);
