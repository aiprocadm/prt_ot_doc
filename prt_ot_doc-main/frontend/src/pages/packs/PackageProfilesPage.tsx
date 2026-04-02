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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.get<Profile[]>("/package-profiles");
      setItems(response.data);
    } catch (nextError) {
      setError((nextError as ApiError) ?? { message: "Не удалось загрузить package profiles" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const createProfile = async () => {
    if (!code || !name) return;
    setError(null);
    try {
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
    } catch (nextError) {
      setError((nextError as ApiError) ?? { message: "Не удалось создать package profile" });
    }
  };

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Package profiles" }]} />
      <Card>
        <CardHeader>
          <CardTitle>Package profiles</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка package profiles" /> : null}
          {!loading ? (
            <div className="flex gap-2">
              <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="code" />
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="name" />
              <Button onClick={() => void createProfile()}>Create</Button>
            </div>
          ) : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Package profiles отсутствуют" description="Создайте первый profile для работы с package presets." />
          ) : null}
          {!loading && items.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {items.map((item) => (
                <li key={item.id}>{item.code} — {item.name} ({item.status})</li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default PackageProfilesPage;
