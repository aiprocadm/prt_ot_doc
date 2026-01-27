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

const navGroups = [
  {
    title: "Основное",
    items: [
      { label: "Главная", to: "/dashboard", icon: LayoutDashboard },
      { label: "Задачи", to: "/tasks", icon: ClipboardCheck },
      { label: "Документы (ЭДО)", to: "/documents", icon: FileText }
    ]
  },
  {
    title: "ОТ и ПромБез",
    items: [
      { label: "Риски", to: "/risk", icon: ShieldAlert },
      { label: "Мероприятия (CAPA)", to: "/activities", icon: Activity },
      { label: "СИЗ и склады", to: "/ppe", icon: Package },
      { label: "Обучение и инструктажи", to: "/training", icon: GraduationCap },
      { label: "Медосмотры/допуски", to: "/medical", icon: HeartPulse },
      { label: "Инциденты/НС", to: "/incidents", icon: AlertTriangle },
      { label: "Проверки/предписания", to: "/inspections", icon: ClipboardCheck },
      { label: "Подготовка к проверке", to: "/audit-prep", icon: Archive }
    ]
  },
  {
    title: "ПБ",
    items: [
      { label: "Объекты защиты", to: "/fire-safety", icon: Flame },
      { label: "Инструктажи/учения", to: "/fire-training", icon: Flame },
      { label: "Проверки/предписания", to: "/fire-inspections", icon: Flame }
    ]
  },
  {
    title: "Справочники",
    items: [{ label: "Опасности, нормы, чек-листы", to: "/reference", icon: Archive }]
  },
  {
    title: "Контрагенты",
    items: [{ label: "Подрядчики", to: "/contractors", icon: Users }]
  },
  {
    title: "Администрирование",
    items: [{ label: "Тенанты и роли", to: "/admin", icon: Wrench }]
  }
];

export const SideNav = () => (
  <aside className="hidden h-[calc(100vh-4rem)] w-72 flex-shrink-0 border-r bg-background/95 px-4 py-6 lg:sticky lg:top-16 lg:block">
    <div className="flex items-center gap-2 text-lg font-semibold">
      <Building2 className="h-5 w-5 text-primary" />
      OT/ПБ Контур
    </div>
    <nav className="mt-6 space-y-6 text-sm">
      {navGroups.map((group) => (
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
