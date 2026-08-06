import { useEffect } from "react";

import { ListStateGuard } from "@/components/common/ListStateGuard";
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
      <Breadcrumb
        items={[
          { label: "Главная", to: ROUTES.DASHBOARD },
          { label: "Пакеты" },
        ]}
      />
      <RegistryPageHeader
        title="Пакеты"
        description="Генерация наборов документов и управление профилями пакетов."
        stats={[
          { label: "Всего пакетов", value: pagination.total },
          { label: "На странице", value: items.length },
        ]}
      />
      <PackWizard />
      <Card>
        <CardContent className="py-6">
          <ListStateGuard
            error={error}
            loading={loading}
            itemsCount={items.length}
            loadingLabel="Загрузка пакетов"
            emptyTitle="Пакеты не найдены"
            emptyDescription="Создайте первый пакет через мастер генерации."
            onRetry={() => void list()}
          >
            <PackTable />
          </ListStateGuard>
        </CardContent>
      </Card>
    </div>
  );
};

export default PacksPage;
