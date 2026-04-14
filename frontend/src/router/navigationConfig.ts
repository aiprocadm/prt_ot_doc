import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertTriangle,
  Archive,
  BookOpen,
  Briefcase,
  Building2,
  ClipboardCheck,
  FileArchive,
  FileText,
  Flame,
  GraduationCap,
  HeartPulse,
  History,
  Link2,
  LayoutDashboard,
  Package,
  Search,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Truck,
  Users,
  Wrench
} from "lucide-react";

import { PERMISSIONS, type Permission } from "@/permissions/permissions";

export type NavItem = {
  label: string;
  to: string;
  icon: LucideIcon;
  permission: Permission;
};

export type NavGroup = {
  title: string;
  items: NavItem[];
};

export const MAIN_NAV_GROUPS: NavGroup[] = [
  {
    title: "Документооборот",
    items: [
      { label: "Главная", to: "/dashboard", icon: LayoutDashboard, permission: PERMISSIONS.DASHBOARD_VIEW },
      { label: "Компании", to: "/companies", icon: Building2, permission: PERMISSIONS.COMPANY_VIEW },
      { label: "Сотрудники", to: "/persons", icon: Users, permission: PERMISSIONS.PERSON_VIEW },
      { label: "Документы", to: "/documents", icon: FileText, permission: PERMISSIONS.DOCUMENT_VIEW },
      { label: "Шаблоны", to: "/templates", icon: FileArchive, permission: PERMISSIONS.TEMPLATE_VIEW },
      { label: "Пакеты", to: "/packs", icon: Package, permission: PERMISSIONS.PACK_VIEW },
      { label: "Генерация", to: "/generation", icon: ClipboardCheck, permission: PERMISSIONS.DOCUMENT_CREATE },
      { label: "Быстрая генерация", to: "/documents/quick-generate", icon: ClipboardCheck, permission: PERMISSIONS.DOCUMENT_CREATE },
      { label: "Пайплайны и задания", to: "/pipelines/runs", icon: Archive, permission: PERMISSIONS.DOCUMENT_VIEW },
      { label: "Архив", to: "/archive", icon: FileArchive, permission: PERMISSIONS.FILE_VIEW },
      { label: "Поиск", to: "/search", icon: Search, permission: PERMISSIONS.FILE_VIEW },
      { label: "Центр внимания", to: "/workspace/attention", icon: AlertTriangle, permission: PERMISSIONS.DASHBOARD_VIEW },
      { label: "Качество данных", to: "/workspace/data-quality", icon: ClipboardCheck, permission: PERMISSIONS.DOCUMENT_VIEW },
      { label: "Экспорты", to: "/exports", icon: Archive, permission: PERMISSIONS.REPORTS_VIEW },
      { label: "Задачи", to: "/tasks", icon: ClipboardCheck, permission: PERMISSIONS.TASK_VIEW },
      { label: "Уведомления", to: "/notifications", icon: AlertTriangle, permission: PERMISSIONS.TASK_VIEW },
      { label: "Календарь", to: "/calendar", icon: Activity, permission: PERMISSIONS.TASK_VIEW }
    ]
  },
  {
    title: "ЭДО и согласования",
    items: [
      { label: "Согласования", to: "/approvals/inbox", icon: ClipboardCheck, permission: PERMISSIONS.DOCUMENT_VIEW },
      { label: "Маршруты согласования", to: "/approval-routes", icon: ClipboardCheck, permission: PERMISSIONS.DOCUMENT_VIEW },
      { label: "Подписи", to: "/signatures", icon: FileText, permission: PERMISSIONS.DOCUMENT_VIEW },
      { label: "ЭДО", to: "/edo", icon: Archive, permission: PERMISSIONS.DOCUMENT_VIEW }
    ]
  },
  {
    title: "ОТ и ПромБез",
    items: [
      { label: "Риски", to: "/risk", icon: ShieldAlert, permission: PERMISSIONS.RISK_VIEW },
      { label: "Мероприятия (CAPA)", to: "/activities", icon: Activity, permission: PERMISSIONS.ACTIVITY_VIEW },
      { label: "СИЗ", to: "/ppe", icon: Package, permission: PERMISSIONS.PPE_VIEW },
      { label: "Склад СИЗ", to: "/warehouse", icon: Truck, permission: PERMISSIONS.WAREHOUSE_VIEW },
      { label: "Обучение", to: "/training", icon: GraduationCap, permission: PERMISSIONS.TRAINING_VIEW },
      { label: "Инструктажи", to: "/briefings", icon: GraduationCap, permission: PERMISSIONS.TRAINING_VIEW },
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
    title: "Бизнес и аналитика",
    items: [
      { label: "CRM / Финансы", to: "/crm-finance", icon: Briefcase, permission: PERMISSIONS.CRM_FINANCE_VIEW },
      { label: "НПА / Нормативная база", to: "/npa", icon: BookOpen, permission: PERMISSIONS.NPA_VIEW },
      { label: "Отчёты", to: "/reports", icon: ShieldCheck, permission: PERMISSIONS.REPORTS_VIEW },
      { label: "Тренды", to: "/analytics/trends", icon: Activity, permission: PERMISSIONS.REPORTS_VIEW },
      { label: "Кабинет клиента", to: "/client-portal/dashboard", icon: Users, permission: PERMISSIONS.CLIENT_PORTAL_VIEW }
    ]
  },
  {
    title: "Интеграции и справочники",
    items: [
      { label: "Интеграции", to: "/integrations", icon: Link2, permission: PERMISSIONS.INTEGRATIONS_VIEW },
      { label: "Опасности, нормы, чек-листы", to: "/reference", icon: Archive, permission: PERMISSIONS.REFERENCE_VIEW },
      { label: "Подрядчики", to: "/contractors", icon: Users, permission: PERMISSIONS.CONTRACTOR_VIEW }
    ]
  },
  {
    title: "Администрирование",
    items: [
      { label: "Тенанты и роли", to: "/admin", icon: Wrench, permission: PERMISSIONS.ADMIN_MANAGE_ROLES },
      { label: "Биллинг", to: "/admin/billing", icon: Briefcase, permission: PERMISSIONS.ADMIN_MANAGE_ROLES },
      { label: "Исходящая очередь", to: "/admin/outbox", icon: Archive, permission: PERMISSIONS.ADMIN_MANAGE_ROLES },
      { label: "Журнал аудита", to: "/audit", icon: History, permission: PERMISSIONS.AUDIT_VIEW },
      { label: "Настройки", to: "/settings", icon: Settings, permission: PERMISSIONS.SETTINGS_VIEW },
      { label: "Синхронизация (offline)", to: "/help/sync-conflicts", icon: History, permission: PERMISSIONS.SETTINGS_VIEW }
    ]
  }
];

export const CLIENT_PORTAL_NAV_GROUPS: NavGroup[] = [
  {
    title: "Кабинет клиента",
    items: [
      { label: "Обзор", to: "/client-portal/dashboard", icon: Users, permission: PERMISSIONS.CLIENT_PORTAL_VIEW },
      { label: "Пакеты", to: "/client-portal/packages", icon: Package, permission: PERMISSIONS.CLIENT_PORTAL_VIEW },
      { label: "Документы", to: "/client-portal/documents", icon: FileText, permission: PERMISSIONS.CLIENT_PORTAL_VIEW },
      { label: "История", to: "/client-portal/history", icon: History, permission: PERMISSIONS.CLIENT_PORTAL_VIEW },
      { label: "Запросы", to: "/client-portal/requests", icon: ClipboardCheck, permission: PERMISSIONS.CLIENT_PORTAL_VIEW }
    ]
  }
];

