import { useEffect } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { FileTable } from "@/features/files/FileTable";
import { FileUploader } from "@/features/files/FileUploader";
import { useFilesStore } from "@/stores/files";

const FilesPage = () => {
  const { list, items, loading, error } = useFilesStore();

  useEffect(() => {
    void list();
  }, [list]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Файлы" }]} />
      <FileUploader />
      <Card>
        <CardContent className="py-6">
          <ErrorState error={error ?? undefined} onRetry={() => void list()} />
          {loading && items.length === 0 ? <LoadingScreen label="Загрузка файлов" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Файлы не найдены" description="Загрузите первый файл или проверьте активные фильтры." />
          ) : null}
          {!loading || items.length > 0 ? <FileTable /> : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default FilesPage;
