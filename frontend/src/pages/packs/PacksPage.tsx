import { useEffect } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";
import { PackTable } from "@/features/packs/PackTable";
import { PackWizard } from "@/features/packs/PackWizard";
import { usePacksStore } from "@/stores/packs";

const PacksPage = () => {
  const { list } = usePacksStore();

  useEffect(() => {
    list();
  }, [list]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/" }, { label: "Пакеты" }]} />
      <PackWizard />
      <Card>
        <CardContent className="py-6">
          <PackTable />
        </CardContent>
      </Card>
    </div>
  );
};

export default PacksPage;
