import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const GeneratePackWizardPage = () => {
  const { presetId = "" } = useParams();
  const navigate = useNavigate();
  const [rowsJson, setRowsJson] = useState('[{"doc":"Акт"}]');
  const [idempotencyKey, setIdempotencyKey] = useState(`wizard-${Date.now()}`);

  const runPack = async () => {
    const rows = JSON.parse(rowsJson) as Array<Record<string, unknown>>;
    const response = await apiClient.post<{ pack_run_id: string }>(
      "/pack-runs",
      {
        package_preset_id: presetId,
        rows,
        selected_rows: rows.map((_, index) => index + 1)
      },
      { headers: { "Idempotency-Key": idempotencyKey } }
    );
    navigate(`/pack-runs/${response.data.pack_run_id}`);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Generate pack wizard</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input value={idempotencyKey} onChange={(e) => setIdempotencyKey(e.target.value)} placeholder="Idempotency key" />
        <textarea className="min-h-48 w-full rounded border p-2 text-sm" value={rowsJson} onChange={(e) => setRowsJson(e.target.value)} />
        <Button onClick={() => void runPack()}>Run pack</Button>
      </CardContent>
    </Card>
  );
};

export default GeneratePackWizardPage;
