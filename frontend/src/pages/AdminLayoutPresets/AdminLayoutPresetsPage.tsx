import { Breadcrumb } from "@/components/ui/breadcrumb";
import { LayoutPresetEditor } from "@/components/LayoutPresetEditor/LayoutPresetEditor";

const AdminLayoutPresetsPage = () => (
  <div className="space-y-6">
    <Breadcrumb
      items={[
        { label: "Главная", to: "/dashboard" },
        { label: "Администрирование", to: "/admin" },
        { label: "Макеты/Колонтитулы" },
      ]}
    />
    <LayoutPresetEditor />
  </div>
);

export default AdminLayoutPresetsPage;
