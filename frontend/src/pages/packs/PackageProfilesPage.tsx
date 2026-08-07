import { useEffect, useState } from "react";

import { packsApi } from "@/api/packs";
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
      const response = await packsApi.getProfiles<Profile>();
      setItems(response);
    } catch (nextError) {
      setError(
        (nextError as ApiError) ?? {
          message: "Не удалось загрузить профили пакетов",
        },
      );
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
      await packsApi.createProfile({
        code,
        name,
        status: "active",
        pipeline_steps_json: [
          { step: "render_docx", enabled: true },
          { step: "convert_pdf", enabled: true },
          { step: "build_zip", enabled: true },
        ],
      });
      setCode("");
      setName("");
      await load();
    } catch (nextError) {
      setError(
        (nextError as ApiError) ?? {
          message: "Не удалось создать профиль пакета",
        },
      );
    }
  };

  return (
    <div className="space-y-4">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Профили пакетов" },
        ]}
      />
      <Card>
        <CardHeader>
          <CardTitle>Профили пакетов</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка профилей пакетов" /> : null}
          {!loading ? (
            <div className="flex gap-2">
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Код"
              />
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Название"
              />
              <Button onClick={() => void createProfile()}>Создать</Button>
            </div>
          ) : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState
              title="Профили пакетов отсутствуют"
              description="Создайте первый профиль для работы с пресетами пакетов."
            />
          ) : null}
          {!loading && items.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {items.map((item) => (
                <li key={item.id}>
                  {item.code} — {item.name} ({item.status})
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default PackageProfilesPage;
