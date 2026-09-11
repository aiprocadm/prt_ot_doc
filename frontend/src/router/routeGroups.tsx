import type { ReactElement } from "react";
import { Route } from "react-router-dom";

import { PERMISSIONS, type Permission } from "@/permissions/permissions";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import {
  documentCreateRoutes,
  documentReadRoutes,
} from "@/router/features/documentRoutes";
import { searchAndFilesRoutes } from "@/router/features/searchAndFilesRoutes";
import {
  ActivitiesPage,
  CommitteeKpiPage,
  ClientCardPage,
  ClientCockpitPage,
  CommitteesPage,
  SoutPage,
  AdminLayoutPresetsPage,
  AdminPage,
  AuditPage,
  AuditPrepPage,
  BillingPage,
  BriefingsPage,
  BudgetPage,
  ImportsPage,
  InternshipsPage,
  CalendarPage,
  ClientDeliveryDashboardPage,
  ClientPortalDashboardPage,
  ClientPortalDocumentsPage,
  ClientPortalHistoryPage,
  ClientPortalPackagesPage,
  ClientPortalRequestsPage,
  CommandCenterPage,
  BranchesPage,
  CompaniesPage,
  ContractorsPage,
  ContractorDetailPage,
  CorrectiveActionsPage,
  CrmFinancePage,
  DashboardPage,
  EmployeeCardPage,
  ExecutiveDashboardPage,
  ExportsPage,
  FindingsPage,
  FireInspectionsPage,
  FireSafetyPage,
  CivilDefensePage,
  EcologyPage,
  RoadSafetyPage,
  IndustrialSafetyPage,
  FireTrainingPage,
  IncidentsPage,
  InspectionChecklistsPage,
  InspectionPlansPage,
  InspectionPrepPackagesPage,
  InspectionsPage,
  HealthStatusPage,
  IntegrationsPage,
  ManagementDashboardPage,
  MedicalPage,
  MobileIssuePage,
  NotificationsPage,
  NpaPage,
  RequirementsPage,
  OutboxPage,
  PacksPage,
  QuickPackWizardPage,
  PersonsPage,
  PortalRequestsPage,
  PpeDashboardPage,
  PpePage,
  PermitsPage,
  PrescriptionsPage,
  ReferencePage,
  SiteCardPage,
  SitesPage,
  ReportBuilderPage,
  ReportsPage,
  RiskPage,
  RulesPage,
  SafetyDashboardPage,
  SettingsPage,
  SyncConflictHelpPage,
  TasksPage,
  TemplatesPage,
  BrandSettingsPage,
  TenantsPage,
  TrainingDashboardPage,
  TrainingPage,
  TrendsPage,
  WarehousePage,
  WorkflowPage,
  WorkPermitDetailPage,
  WorkPermitsPage,
  WorkspaceAttentionPage,
  WorkspaceDataQualityPage,
} from "@/router/pageRegistry";

type GuardedRouteGroup = {
  permission: Permission;
  routes: ReactElement[];
};

const renderGuardedGroup = ({ permission, routes }: GuardedRouteGroup) => (
  <Route key={permission} element={<ProtectedRoute permission={permission} />}>
    {routes}
  </Route>
);

export const buildProtectedRouteGroups = (): ReactElement[] => {
  const groups: GuardedRouteGroup[] = [
    {
      permission: PERMISSIONS.DASHBOARD_VIEW,
      routes: [
        <Route
          key="/dashboard"
          path="/dashboard"
          element={<DashboardPage />}
        />,
        <Route
          key="/dashboard/executive"
          path="/dashboard/executive"
          element={<ExecutiveDashboardPage />}
        />,
        <Route
          key="/dashboard/safety"
          path="/dashboard/safety"
          element={<SafetyDashboardPage />}
        />,
        <Route
          key="/dashboard/training"
          path="/dashboard/training"
          element={<TrainingDashboardPage />}
        />,
        <Route
          key="/dashboard/ppe"
          path="/dashboard/ppe"
          element={<PpeDashboardPage />}
        />,
        <Route
          key="/dashboard/client-delivery"
          path="/dashboard/client-delivery"
          element={<ClientDeliveryDashboardPage />}
        />,
        <Route
          key="/command-center"
          path="/command-center"
          element={<CommandCenterPage />}
        />,
        <Route
          key="/workspace/attention"
          path="/workspace/attention"
          element={<WorkspaceAttentionPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.DATA_QUALITY_VIEW,
      routes: [
        <Route
          key="/workspace/data-quality"
          path="/workspace/data-quality"
          element={<WorkspaceDataQualityPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.COMPANY_VIEW,
      routes: [
        <Route
          key="/companies"
          path="/companies"
          element={<CompaniesPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.BRANCH_VIEW,
      routes: [
        <Route key="/branches" path="/branches" element={<BranchesPage />} />,
      ],
    },
    {
      permission: PERMISSIONS.PERSON_VIEW,
      routes: [
        <Route key="/persons" path="/persons" element={<PersonsPage />} />,
      ],
    },
    {
      permission: PERMISSIONS.EMPLOYEE_CARD_VIEW,
      routes: [
        <Route
          key="/employees/:personId"
          path="/employees/:personId"
          element={<EmployeeCardPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.TEMPLATE_VIEW,
      routes: [
        <Route
          key="/templates"
          path="/templates"
          element={<TemplatesPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.PACK_VIEW,
      routes: [
        <Route key="/packs" path="/packs" element={<PacksPage />} />,
        // Мастер разового комплекта (ТЗ разд. 50.2). Конкретный путь объявлен
        // ДО «/packs», иначе он был бы съеден маршрутом реестра.
        <Route
          key="/packs/wizard"
          path="/packs/wizard"
          element={<QuickPackWizardPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.DOCUMENT_VIEW,
      routes: documentReadRoutes(),
    },
    {
      permission: PERMISSIONS.DOCUMENT_CREATE,
      routes: documentCreateRoutes(),
    },
    {
      permission: PERMISSIONS.FILE_VIEW,
      routes: searchAndFilesRoutes(),
    },
    {
      permission: PERMISSIONS.TASK_VIEW,
      routes: [
        <Route key="/tasks" path="/tasks" element={<TasksPage />} />,
        <Route key="/workflow" path="/workflow" element={<WorkflowPage />} />,
        <Route
          key="/notifications"
          path="/notifications"
          element={<NotificationsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.CALENDAR_VIEW,
      routes: [
        <Route key="/calendar" path="/calendar" element={<CalendarPage />} />,
      ],
    },
    {
      permission: PERMISSIONS.RISK_VIEW,
      routes: [<Route key="/risk" path="/risk" element={<RiskPage />} />],
    },
    {
      permission: PERMISSIONS.ACTIVITY_VIEW,
      routes: [
        <Route
          key="/activities"
          path="/activities"
          element={<ActivitiesPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.PPE_VIEW,
      routes: [<Route key="/ppe" path="/ppe" element={<PpePage />} />],
    },
    {
      permission: PERMISSIONS.PPE_ISSUE,
      routes: [
        <Route
          key="/ppe/issue"
          path="/ppe/issue"
          element={<MobileIssuePage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.WAREHOUSE_VIEW,
      routes: [
        <Route
          key="/warehouse"
          path="/warehouse"
          element={<WarehousePage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.TRAINING_VIEW,
      routes: [
        <Route key="/training" path="/training" element={<TrainingPage />} />,
        <Route
          key="/briefings"
          path="/briefings"
          element={<BriefingsPage />}
        />,
        <Route
          key="/internships"
          path="/internships"
          element={<InternshipsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.MEDICAL_VIEW,
      routes: [
        <Route key="/medical" path="/medical" element={<MedicalPage />} />,
      ],
    },
    {
      permission: PERMISSIONS.INCIDENT_VIEW,
      routes: [
        <Route
          key="/incidents"
          path="/incidents"
          element={<IncidentsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.INSPECTION_VIEW,
      routes: [
        <Route
          key="/inspections"
          path="/inspections"
          element={<InspectionsPage />}
        />,
        <Route
          key="/inspection-plans"
          path="/inspection-plans"
          element={<InspectionPlansPage />}
        />,
        <Route
          key="/inspection-checklists"
          path="/inspection-checklists"
          element={<InspectionChecklistsPage />}
        />,
        <Route key="/findings" path="/findings" element={<FindingsPage />} />,
        <Route
          key="/prescriptions"
          path="/prescriptions"
          element={<PrescriptionsPage />}
        />,
        <Route
          key="/corrective-actions"
          path="/corrective-actions"
          element={<CorrectiveActionsPage />}
        />,
        <Route
          key="/inspection-prep/packages"
          path="/inspection-prep/packages"
          element={<InspectionPrepPackagesPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.PERMIT_VIEW,
      routes: [
        <Route key="/permits" path="/permits" element={<PermitsPage />} />,
      ],
    },
    {
      permission: PERMISSIONS.AUDIT_PREP_VIEW,
      routes: [
        <Route
          key="/audit-prep"
          path="/audit-prep"
          element={<AuditPrepPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.FIRE_SAFETY_VIEW,
      routes: [
        <Route
          key="/fire-safety"
          path="/fire-safety"
          element={<FireSafetyPage />}
        />,
      ],
    },
    {
      // Доп. №1 разд. 55: реестр объектов НВОС — первый экран контура экологии.
      permission: PERMISSIONS.ECOLOGY_VIEW,
      routes: [
        <Route key="/ecology" path="/ecology" element={<EcologyPage />} />,
      ],
    },
    {
      // Доп. №1 разд. 56.1: реестр формирований — первый экран контура ГО и ЧС.
      permission: PERMISSIONS.CIVIL_DEFENSE_VIEW,
      routes: [
        <Route
          key="/civil-defense"
          path="/civil-defense"
          element={<CivilDefensePage />}
        />,
      ],
    },
    {
      // Доп. №1 разд. 56.2: реестр ТС — первый экран контура БДД.
      permission: PERMISSIONS.ROAD_SAFETY_VIEW,
      routes: [
        <Route
          key="/road-safety"
          path="/road-safety"
          element={<RoadSafetyPage />}
        />,
      ],
    },
    {
      // Доп. №1 разд. 54.2: реестр ОПО — первый экран контура ПромБеза.
      permission: PERMISSIONS.INDUSTRIAL_SAFETY_VIEW,
      routes: [
        <Route
          key="/industrial-safety"
          path="/industrial-safety"
          element={<IndustrialSafetyPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.FIRE_TRAINING_VIEW,
      routes: [
        <Route
          key="/fire-training"
          path="/fire-training"
          element={<FireTrainingPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.FIRE_INSPECTIONS_VIEW,
      routes: [
        <Route
          key="/fire-inspections"
          path="/fire-inspections"
          element={<FireInspectionsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.REFERENCE_VIEW,
      routes: [
        <Route
          key="/reference"
          path="/reference"
          element={<ReferencePage />}
        />,
        // Площадки — справочник предприятия, поэтому право то же. Карточка
        // 360° живёт ЗДЕСЬ, а не в модуле дисциплины: она про все дисциплины
        // сразу, и выключение «Пожарной безопасности» не должно её прятать.
        <Route key="/sites" path="/sites" element={<SitesPage />} />,
        <Route
          key="/sites/:siteId"
          path="/sites/:siteId"
          element={<SiteCardPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.CONTRACTOR_VIEW,
      routes: [
        <Route
          key="/contractors"
          path="/contractors"
          element={<ContractorsPage />}
        />,
        <Route
          key="/contractors/:id"
          path="/contractors/:id"
          element={<ContractorDetailPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.WORK_PERMIT_VIEW,
      routes: [
        <Route
          key="/work-permits"
          path="/work-permits"
          element={<WorkPermitsPage />}
        />,
        <Route
          key="/work-permits/:id"
          path="/work-permits/:id"
          element={<WorkPermitDetailPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.ADMIN_MANAGE_ROLES,
      routes: [
        <Route key="/admin" path="/admin" element={<AdminPage />} />,
        <Route
          key="/admin/outbox"
          path="/admin/outbox"
          element={<OutboxPage />}
        />,
        <Route
          key="/admin/health"
          path="/admin/health"
          element={<HealthStatusPage />}
        />,
        <Route
          key="/admin/billing"
          path="/admin/billing"
          element={<BillingPage />}
        />,
        <Route
          key="/admin/layout-presets"
          path="/admin/layout-presets"
          element={<AdminLayoutPresetsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.ADMIN_MANAGE_TENANTS,
      routes: [
        <Route
          key="/admin/tenants"
          path="/admin/tenants"
          element={<TenantsPage />}
        />,
        // BIZ-52 разд. 52.2: настройка бренда партнёром. Право то же, что у
        // кабинета клиентов: кто ведёт свой контур, тот его и оформляет.
        <Route
          key="/admin/branding"
          path="/admin/branding"
          element={<BrandSettingsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.NPA_VIEW,
      routes: [
        <Route key="/npa" path="/npa" element={<NpaPage />} />,
        // Срез-145 (B.18 разд. 19.2): реестр требований — обязанности,
        // выведенные из актов; право то же, что у реестра НПА.
        <Route
          key="/npa/requirements"
          path="/npa/requirements"
          element={<RequirementsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.AUDIT_VIEW,
      routes: [<Route key="/audit" path="/audit" element={<AuditPage />} />],
    },
    {
      permission: PERMISSIONS.SETTINGS_VIEW,
      routes: [
        <Route key="/settings" path="/settings" element={<SettingsPage />} />,
        <Route
          key="/help/sync-conflicts"
          path="/help/sync-conflicts"
          element={<SyncConflictHelpPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.REPORTS_VIEW,
      routes: [
        <Route key="/reports" path="/reports" element={<ReportsPage />} />,
        <Route
          key="/reports/builder"
          path="/reports/builder"
          element={<ReportBuilderPage />}
        />,
        <Route key="/exports" path="/exports" element={<ExportsPage />} />,
        <Route
          key="/analytics/trends"
          path="/analytics/trends"
          element={<TrendsPage />}
        />,
        <Route
          key="/portal-requests"
          path="/portal-requests"
          element={<PortalRequestsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.ANALYTICS_VIEW,
      routes: [
        <Route
          key="/analytics"
          path="/analytics"
          element={<ManagementDashboardPage />}
        />,
        // Срез-3: KPI комитетов — под management-правом ANALYTICS_VIEW, а не COMMITTEE_VIEW.
        // React Router v6 ранжирует по специфичности, поэтому /committees/kpi не конфликтует
        // с /committees из группы COMMITTEE_VIEW.
        <Route
          key="/committees/kpi"
          path="/committees/kpi"
          element={<CommitteeKpiPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.CLIENT_PORTAL_VIEW,
      routes: [
        <Route
          key="/client-portal/dashboard"
          path="/client-portal/dashboard"
          element={<ClientPortalDashboardPage />}
        />,
        <Route
          key="/client-portal/packages"
          path="/client-portal/packages"
          element={<ClientPortalPackagesPage />}
        />,
        <Route
          key="/client-portal/documents"
          path="/client-portal/documents"
          element={<ClientPortalDocumentsPage />}
        />,
        <Route
          key="/client-portal/history"
          path="/client-portal/history"
          element={<ClientPortalHistoryPage />}
        />,
        <Route
          key="/client-portal/requests"
          path="/client-portal/requests"
          element={<ClientPortalRequestsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.CRM_FINANCE_VIEW,
      routes: [
        <Route
          key="/crm-finance"
          path="/crm-finance"
          element={<CrmFinancePage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.INTEGRATIONS_VIEW,
      routes: [
        <Route
          key="/integrations"
          path="/integrations"
          element={<IntegrationsPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.COMMITTEE_VIEW,
      routes: [
        <Route
          key="/committees"
          path="/committees"
          element={<CommitteesPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.MANAGED_CLIENTS_VIEW,
      routes: [
        <Route
          key="/managed-clients"
          path="/managed-clients"
          element={<ClientCockpitPage />}
        />,
        <Route
          key="/managed-clients/:clientId"
          path="/managed-clients/:clientId"
          element={<ClientCardPage />}
        />,
      ],
    },
    {
      permission: PERMISSIONS.SOUT_VIEW,
      routes: [<Route key="/sout" path="/sout" element={<SoutPage />} />],
    },
    {
      permission: PERMISSIONS.RULES_VIEW,
      routes: [<Route key="/rules" path="/rules" element={<RulesPage />} />],
    },
    {
      permission: PERMISSIONS.BUDGET_VIEW,
      routes: [<Route key="/budget" path="/budget" element={<BudgetPage />} />],
    },
    {
      permission: PERMISSIONS.IMPORTS_MANAGE,
      routes: [
        <Route key="/imports" path="/imports" element={<ImportsPage />} />,
      ],
    },
  ];

  return groups.map(renderGuardedGroup);
};
