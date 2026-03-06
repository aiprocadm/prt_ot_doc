import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface Preset {
  id: string;
  code: string;
  name: string;
  status: string;
}

interface Profile {
  id: string;
  code: string;
}

const PackagePresetsPage = () => {
  const [items, setItems] = useState<Preset[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");

  const load = async () => {
    const [presets, profileRows] = await Promise.all([
      apiClient.get<Preset[]>("/package-presets"),
      apiClient.get<Profile[]>("/package-profiles")
    ]);
    setItems(presets.data);
    setProfiles(profileRows.data);
  };

  useEffect(() => {
    void load();
  }, []);

  const createPreset = async () => {
    if (!profiles.length || !code || !name) return;
    await apiClient.post("/package-presets", {
      code,
      name,
      package_profile_id: profiles[0].id,
      naming_rule: "<doc>_<date>",
      source_type: "json",
      mapping_json: { doc: { type: "literal", value: "pack" } },
      status: "active"
    });
    setCode("");
    setName("");
    await load();
  };

  const validatePreset = async (id: string) => {
    await apiClient.post(`/package-presets/${id}:validate`);
    await load();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Package presets</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="code" />
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="name" />
          <Button onClick={() => void createPreset()}>Create</Button>
        </div>
        <ul className="space-y-1 text-sm">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-2">
              <span>{item.code} — {item.name} ({item.status})</span>
              <Button size="sm" variant="outline" onClick={() => void validatePreset(item.id)}>Validate</Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
};

export default PackagePresetsPage;
