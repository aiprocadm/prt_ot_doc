import { BookmarkPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { SearchTab, SearchFacets } from "../types";

type Props = {
  query: string;
  type: SearchTab;
  tabs: SearchTab[];
  facets: SearchFacets;
  onQueryChange: (value: string) => void;
  onTypeChange: (value: SearchTab) => void;
  onSaveSearch: () => Promise<void>;
};

export const SearchQueryPanel = ({ query, type, tabs, facets, onQueryChange, onTypeChange, onSaveSearch }: Props) => (
  <Card>
    <CardContent className="space-y-4 py-6">
      <Input value={query} placeholder="Поиск по системе" onChange={(e) => onQueryChange(e.target.value)} />
      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <Button key={tab} variant={tab === type ? "default" : "outline"} size="sm" onClick={() => onTypeChange(tab)}>
            {tab} ({facets.type_counts?.[tab] ?? facets.type_counts?.[tab.replace(/s$/, "")] ?? 0})
          </Button>
        ))}
        <Button variant="outline" size="sm" onClick={() => void onSaveSearch()}>
          <BookmarkPlus className="mr-2 h-4 w-4" /> Сохранить поиск
        </Button>
      </div>
    </CardContent>
  </Card>
);
