import { useEffect } from "react";

import { ListStateGuard } from "@/components/common/ListStateGuard";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { FileTable } from "@/features/files/FileTable";
import { FileUploader } from "@/features/files/FileUploader";
import { useFilesStore } from "@/stores/files";
import { ROUTES } from "@/router/routes";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import { trackUxMetric } from "@/utils/uxMetrics";

const FilesPage = () => {
  const { list, items, loading, error } = useFilesStore();

  useEffect(() => {
    void list();
  }, [list]);

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[{ label: "Главная", to: ROUTES.DASHBOARD }, { label: "Файлы" }]}
      />
      <FileUploader />
      <Card>
        <CardContent className="py-6">
          <ListStateGuard
            error={error}
            loading={loading}
            itemsCount={items.length}
            loadingLabel="Загрузка файлов"
            emptyTitle="Файлы не найдены"
            emptyDescription="Загрузите первый файл или проверьте активные фильтры."
            onRetry={() => void list()}
            emptyAction={
              <Button asChild>
                <Link
                  to="/documents"
                  onClick={() => {
                    trackUxMetric("empty_state_to_action_rate", {
                      source: "files",
                      action: "open_documents",
                    });
                    trackUxMetric("time_to_first_action", {
                      source: "files_empty_state",
                    });
                  }}
                >
                  Перейти к документам
                </Link>
              </Button>
            }
          >
            <FileTable />
          </ListStateGuard>
        </CardContent>
      </Card>
    </div>
  );
};

export default FilesPage;
