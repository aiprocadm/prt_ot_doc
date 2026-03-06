import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface Profile {
  id: string;
  code: string;
  name: string;
  status: string;
}

const PackageProfilesPage = () => {
  const [items, setItems] = useState<Profile[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");

  const load = async () => {
    const response = await apiClient.get<Profile[]>("/package-profiles");
    setItems(response.data);
  };

  useEffect(() => {
    void load();
  }, []);

  const createProfile = async () => {
    if (!code || !name) return;
    await apiClient.post("/package-profiles", {
      code,
      name,
      status: "active",
      pipeline_steps_json: [
        { step: "render_docx", enabled: true },
        { step: "convert_pdf", enabled: true },
        { step: "build_zip", enabled: true }
      ]
    });
    setCode("");
    setName("");
    await load();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Package profiles</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="code" />
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="name" />
          <Button onClick={() => void createProfile()}>Create</Button>
        </div>
        <ul className="space-y-1 text-sm">
          {items.map((item) => (
            <li key={item.id}>{item.code} — {item.name} ({item.status})</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
};

export default PackageProfilesPage;
