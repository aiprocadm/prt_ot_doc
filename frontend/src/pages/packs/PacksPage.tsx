import { useEffect } from "react";
import { Link } from "react-router-dom";

import { ListStateGuard } from "@/components/common/ListStateGuard";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ROUTES } from "@/router/routes";
import { PackTable } from "@/features/packs/PackTable";
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
      {/* Срез-153: встроенный мастер слал запрос на `POST /packs` — ручки,
          которой у сервера нет вовсе, и предлагал собственные пресеты, не
          совпадающие ни с одним комплектом продукта: кнопка «Запустить»
          всегда кончалась 404. Комплект собирается мастером на отдельной
          странице — он берёт сценарии с сервера и шлёт их в `/packs/run`. */}
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-6">
          <div>
            <div className="font-medium">Собрать комплект документов</div>
            <p className="text-sm text-muted-foreground">
              Мастер спросит сценарий, клиента и только недостающие данные.
            </p>
          </div>
          <Button asChild>
            <Link to="/packs/wizard">Открыть мастер</Link>
          </Button>
        </CardContent>
      </Card>
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
