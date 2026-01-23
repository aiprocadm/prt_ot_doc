import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent } from "@/components/ui/card";

const SettingsPage = () => (
  <div className="space-y-6">
    <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Настройки" }]} />
    <Card>
      <CardContent className="space-y-4 py-6">
        <h2 className="text-xl font-semibold">Настройки профиля</h2>
        <p className="text-sm text-muted-foreground">Раздел в разработке.</p>
      </CardContent>
    </Card>
  </div>
);

export default SettingsPage;
