import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { formatDate } from "@/utils/datetime";

import { useClientPortalPackages } from "./useClientPortalPackages";

const ClientPortalDocumentsPage = () => {
  const { items, selected, loading, error, load, selectRun } =
    useClientPortalPackages();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb
          items={[
            { label: "Главная", to: "/dashboard" },
            { label: "Кабинет клиента" },
            { label: "Файлы" },
          ]}
        />
        <Button
          variant="outline"
          onClick={() => void load()}
          disabled={loading}
        >
          Обновить
        </Button>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка файлов клиента" /> : null}
      {!loading && !error && !items.length ? (
        <EmptyState
          title="Пакеты отсутствуют"
          description="Список файлов станет доступен после публикации пакета."
        />
      ) : null}
      <div className="grid gap-6 lg:grid-cols-[0.9fr_1.4fr]">
        <Card>
          <CardHeader>
            <CardTitle>Пакеты</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {!loading && !error
              ? items.map((item) => (
                  <button
                    key={item.id}
                    className="w-full rounded-lg border p-3 text-left text-sm hover:bg-muted"
                    onClick={() => void selectRun(item.package_id ?? item.id)}
                  >
                    <div className="font-medium">
                      {item.package_id ?? item.id}
                    </div>
                    <div className="text-muted-foreground">
                      {item.started_at
                        ? formatDate(item.started_at)
                        : "Дата запуска недоступна"}
                    </div>
                  </button>
                ))
              : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Артефакты пакета</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!loading && !error && selected?.files.length
              ? selected.files.map((file) => (
                  <div
                    key={`${selected.run.id}-${file.kind}-${file.sha256}`}
                    className="rounded-lg border p-4 text-sm"
                  >
                    <div className="font-medium">{file.kind}</div>
                    <div className="text-muted-foreground">
                      SHA256: {file.sha256 ?? "—"} · Размер: {file.size ?? "—"}
                    </div>
                    {file.signed_url ? (
                      <a
                        className="mt-2 inline-block text-primary underline"
                        href={file.signed_url}
                      >
                        Скачать файл
                      </a>
                    ) : null}
                  </div>
                ))
              : null}
            {!loading &&
            !error &&
            items.length > 0 &&
            !selected?.files.length ? (
              <div className="text-sm text-muted-foreground">
                Выберите пакет, чтобы увидеть доступные файлы.
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default ClientPortalDocumentsPage;
