import { useEffect } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { ROUTES } from "@/router/routes";
import { PackTable } from "@/features/packs/PackTable";
import { PackWizard } from "@/features/packs/PackWizard";
import { usePacksStore } from "@/stores/packs";

const PacksPage = () => {
  const { list, items, loading, error, pagination } = usePacksStore();

  useEffect(() => {
    void list();
  }, [list]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: ROUTES.DASHBOARD }, { label: "Пакеты" }]} />
      <RegistryPageHeader
        title="Пакеты"
        description="Генерация наборов документов и управление профилями пакетов."
        stats={[
          { label: "Всего пакетов", value: pagination.total },
          { label: "На странице", value: items.length }
        ]}
      />
      <PackWizard />
      <Card>
        <CardContent className="py-6">
          <ErrorState error={error ?? undefined} onRetry={() => void list()} />
          {loading && items.length === 0 ? <LoadingScreen label="Загрузка пакетов" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Пакеты не найдены" description="Создайте первый пакет через мастер генерации." />
          ) : null}
          {!loading || items.length > 0 ? <PackTable /> : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default PacksPage;
