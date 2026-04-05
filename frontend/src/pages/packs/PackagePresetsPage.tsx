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
      setError((nextError as ApiError) ?? { message: "Не удалось загрузить пресеты пакетов" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const createPreset = async () => {
    if (!profiles.length || !code || !name) return;
    setError(null);
    try {
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
    } catch (nextError) {
      setError((nextError as ApiError) ?? { message: "Не удалось создать пресет пакета" });
    }
  };

  const validatePreset = async (id: string) => {
    setError(null);
    try {
      await apiClient.post(`/package-presets/${id}:validate`);
      await load();
    } catch (nextError) {
      setError((nextError as ApiError) ?? { message: "Не удалось проверить пресет пакета" });
    }
  };

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Пресеты пакетов" }]} />
      <Card>
        <CardHeader>
          <CardTitle>Пресеты пакетов</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка пресетов пакетов" /> : null}
          {!loading ? (
            <div className="flex gap-2">
              <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Код" />
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название" />
              <Button onClick={() => void createPreset()}>Создать</Button>
            </div>
          ) : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Пресеты пакетов отсутствуют" description="Создайте первый пресет после настройки профиля пакета." />
          ) : null}
          {!loading && items.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-2">
                  <span>{item.code} — {item.name} ({item.status})</span>
                  <Button size="sm" variant="outline" onClick={() => void validatePreset(item.id)}>Проверить</Button>
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
