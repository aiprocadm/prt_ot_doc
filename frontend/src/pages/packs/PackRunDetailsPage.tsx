import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface RunItem {
  id: string;
  row_no: number;
  status: string;
  file_name: string;
  error_code?: string;
}

const PackRunDetailsPage = () => {
  const { id = "" } = useParams();
  const [items, setItems] = useState<RunItem[]>([]);
  const [timeline, setTimeline] = useState<Array<{ id: string; level: string; message: string }>>([]);

  const load = async () => {
    const [itemResp, timelineResp] = await Promise.all([
      apiClient.get<RunItem[]>(`/pack-runs/${id}/items`),
      apiClient.get<Array<{ id: string; level: string; message: string }>>(`/pack-runs/${id}/timeline`)
    ]);
    setItems(itemResp.data);
    setTimeline(timelineResp.data);
  };

  useEffect(() => {
    void load();
  }, [id]);

  const retryFailed = async () => {
    await apiClient.post(`/pack-runs/${id}:retry-failed`);
    await load();
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Pack run items</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Button variant="outline" onClick={() => void retryFailed()}>Retry failed</Button>
          {items.map((item) => (
            <div key={item.id}>{item.row_no}. {item.file_name} — {item.status}</div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          {timeline.map((entry) => (
            <div key={entry.id}>{entry.level}: {entry.message}</div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
};

export default PackRunDetailsPage;
