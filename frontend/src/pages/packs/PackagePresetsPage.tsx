import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ApiError } from "@/types/dto/common";

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [presets, profileRows] = await Promise.all([
        apiClient.get<Preset[]>("/package-presets"),
        apiClient.get<Profile[]>("/package-profiles")
      ]);
      setItems(presets.data);
      setProfiles(profileRows.data);
    } catch (nextError) {
      setError((nextError as ApiError) ?? { message: "Не удалось загрузить package presets" });
    } finally {
      setLoading(false);
    }
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
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Package presets" }]} />
      <Card>
        <CardHeader>
          <CardTitle>Package presets</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка package presets" /> : null}
          {!loading ? (
            <div className="flex gap-2">
              <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="code" />
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="name" />
              <Button onClick={() => void createPreset()}>Create</Button>
            </div>
          ) : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Package presets отсутствуют" description="Создайте первый preset после настройки package profile." />
          ) : null}
          {!loading && !error && items.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-2">
                  <span>{item.code} — {item.name} ({item.status})</span>
                  <Button size="sm" variant="outline" onClick={() => void validatePreset(item.id)}>Validate</Button>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default PackagePresetsPage;
