import { NavLink } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  Archive,
  Building2,
  ClipboardCheck,
  FileText,
  Flame,
  GraduationCap,
  HeartPulse,
  LayoutDashboard,
  Package,
  ShieldAlert,
  Users,
  Wrench
} from "lucide-react";

import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";

const navGroups = [
  {
    title: "Основное",
    items: [
      { label: "Главная", to: "/dashboard", icon: LayoutDashboard, permission: PERMISSIONS.DASHBOARD_VIEW },
      { label: "Задачи", to: "/tasks", icon: ClipboardCheck, permission: PERMISSIONS.TASK_VIEW },
      { label: "Документы (ЭДО)", to: "/documents", icon: FileText, permission: PERMISSIONS.DOCUMENT_VIEW },
      { label: "Отчёты", to: "/reports", icon: Archive, permission: PERMISSIONS.REPORTS_VIEW }
    ]
  },
  {
    title: "ОТ и ПромБез",
    items: [
      { label: "Риски", to: "/risk", icon: ShieldAlert, permission: PERMISSIONS.RISK_VIEW },
      { label: "Мероприятия (CAPA)", to: "/activities", icon: Activity, permission: PERMISSIONS.ACTIVITY_VIEW },
      { label: "СИЗ и склады", to: "/ppe", icon: Package, permission: PERMISSIONS.PPE_VIEW },
      { label: "Обучение и инструктажи", to: "/training", icon: GraduationCap, permission: PERMISSIONS.TRAINING_VIEW },
      { label: "Медосмотры/допуски", to: "/medical", icon: HeartPulse, permission: PERMISSIONS.MEDICAL_VIEW },
      { label: "Инциденты/НС", to: "/incidents", icon: AlertTriangle, permission: PERMISSIONS.INCIDENT_VIEW },
      { label: "Проверки/предписания", to: "/inspections", icon: ClipboardCheck, permission: PERMISSIONS.INSPECTION_VIEW },
      { label: "Подготовка к проверке", to: "/audit-prep", icon: Archive, permission: PERMISSIONS.AUDIT_PREP_VIEW }
    ]
  },
  {
    title: "ПБ",
    items: [
      { label: "Объекты защиты", to: "/fire-safety", icon: Flame, permission: PERMISSIONS.FIRE_SAFETY_VIEW },
      { label: "Инструктажи/учения", to: "/fire-training", icon: Flame, permission: PERMISSIONS.FIRE_TRAINING_VIEW },
      { label: "Проверки/предписания", to: "/fire-inspections", icon: Flame, permission: PERMISSIONS.FIRE_INSPECTIONS_VIEW }
    ]
  },
  {
    title: "Справочники",
    items: [
      { label: "Опасности, нормы, чек-листы", to: "/reference", icon: Archive, permission: PERMISSIONS.REFERENCE_VIEW }
    ]
  },
  {
    title: "Контрагенты",
    items: [{ label: "Подрядчики", to: "/contractors", icon: Users, permission: PERMISSIONS.CONTRACTOR_VIEW }]
  },
  {
    title: "Администрирование",
    items: [{ label: "Тенанты и роли", to: "/admin", icon: Wrench, permission: PERMISSIONS.ADMIN_MANAGE_ROLES }]
  }
];

export const SideNav = () => {
  const { can } = useAbility();
  const visibleGroups = navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => can(item.permission))
    }))
    .filter((group) => group.items.length > 0);

  return (
    <aside className="hidden h-[calc(100vh-4rem)] w-72 flex-shrink-0 border-r bg-background/95 px-4 py-6 lg:sticky lg:top-16 lg:block">
      <div className="flex items-center gap-2 text-lg font-semibold">
        <Building2 className="h-5 w-5 text-primary" />
        OT/ПБ Контур
      </div>
      <nav className="mt-6 space-y-6 text-sm">
        {visibleGroups.map((group) => (
          <div key={group.title} className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.title}</div>
            <div className="space-y-1">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-md px-3 py-2 transition-colors ${
                      isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                    }`
                  }
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
};
