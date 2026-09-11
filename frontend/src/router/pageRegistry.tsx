import { lazy } from "react";

export const LoginPage = lazy(() => import("@/pages/auth/LoginPage"));
export const DashboardPage = lazy(
  () => import("@/pages/dashboard/DashboardPage"),
);
export const CommandCenterPage = lazy(
  () => import("@/pages/operational/CommandCenterPage"),
);
export const CompaniesPage = lazy(
  () => import("@/pages/companies/CompaniesPage"),
);
export const BranchesPage = lazy(() => import("@/pages/branches/BranchesPage"));
export const PersonsPage = lazy(() => import("@/pages/persons/PersonsPage"));
export const EmployeeCardPage = lazy(
  () => import("@/pages/employees/EmployeeCardPage"),
);
export const TemplatesPage = lazy(
  () => import("@/pages/templates/TemplatesPage"),
);
export const PacksPage = lazy(() => import("@/pages/packs/PacksPage"));
export const QuickPackWizardPage = lazy(() =>
  import("@/pages/packs/QuickPackWizardPage").then((module) => ({
    default: module.QuickPackWizardPage,
  })),
);
export const TasksPage = lazy(() => import("@/pages/tasks/TasksPage"));
export const RiskPage = lazy(() => import("@/pages/risk/RiskPage"));
export const ActivitiesPage = lazy(
  () => import("@/pages/activities/ActivitiesPage"),
);
export const PpePage = lazy(() => import("@/pages/ppe/PpePage"));
export const MobileIssuePage = lazy(
  () => import("@/pages/ppe/MobileIssuePage"),
);
export const TrainingPage = lazy(() => import("@/pages/training/TrainingPage"));
export const BriefingsPage = lazy(
  () => import("@/pages/briefings/BriefingsPage"),
);
export const InternshipsPage = lazy(
  () => import("@/pages/internships/InternshipsPage"),
);
export const MedicalPage = lazy(() => import("@/pages/medical/MedicalPage"));
export const IncidentsPage = lazy(
  () => import("@/pages/incidents/IncidentsPage"),
);
export const InspectionsPage = lazy(
  () => import("@/pages/inspections/InspectionsPage"),
);
export const InspectionPlansPage = lazy(
  () => import("@/pages/inspection-plans/InspectionPlansPage"),
);
export const InspectionChecklistsPage = lazy(
  () => import("@/pages/inspection-checklists/InspectionChecklistsPage"),
);
export const FindingsPage = lazy(() => import("@/pages/findings/FindingsPage"));
export const PrescriptionsPage = lazy(
  () => import("@/pages/prescriptions/PrescriptionsPage"),
);
export const PermitsPage = lazy(() => import("@/pages/permits/PermitsPage"));
export const CorrectiveActionsPage = lazy(
  () => import("@/pages/corrective-actions/CorrectiveActionsPage"),
);
export const InspectionPrepPackagesPage = lazy(
  () => import("@/pages/inspection-prep/InspectionPrepPackagesPage"),
);
export const AuditPrepPage = lazy(
  () => import("@/pages/audit-prep/AuditPrepPage"),
);
export const FireSafetyPage = lazy(
  () => import("@/pages/fire-safety/FireSafetyPage"),
);
export const FireTrainingPage = lazy(
  () => import("@/pages/fire-training/FireTrainingPage"),
);
export const FireInspectionsPage = lazy(
  () => import("@/pages/fire-inspections/FireInspectionsPage"),
);
export const IndustrialSafetyPage = lazy(
  () => import("@/pages/industrial-safety/IndustrialSafetyPage"),
);
export const EcologyPage = lazy(() => import("@/pages/ecology/EcologyPage"));
export const CivilDefensePage = lazy(
  () => import("@/pages/civilDefense/CivilDefensePage"),
);
export const RoadSafetyPage = lazy(
  () => import("@/pages/roadSafety/RoadSafetyPage"),
);
export const ReferencePage = lazy(
  () => import("@/pages/reference/ReferencePage"),
);
export const ContractorsPage = lazy(
  () => import("@/pages/contractors/ContractorsPage"),
);
export const ContractorDetailPage = lazy(
  () => import("@/pages/contractors/ContractorDetailPage"),
);
export const AdminPage = lazy(() => import("@/pages/admin/AdminPage"));
export const OutboxPage = lazy(() => import("@/pages/admin/OutboxPage"));
export const HealthStatusPage = lazy(
  () => import("@/pages/admin/HealthStatusPage"),
);
export const BillingPage = lazy(() => import("@/pages/admin/BillingPage"));
export const TenantsPage = lazy(() => import("@/pages/admin/TenantsPage"));
export const BrandSettingsPage = lazy(
  () => import("@/pages/admin/BrandSettingsPage"),
);
export const AdminLayoutPresetsPage = lazy(
  () => import("@/pages/AdminLayoutPresets/AdminLayoutPresetsPage"),
);
export const NpaPage = lazy(() => import("@/pages/npa/NpaPage"));
export const RequirementsPage = lazy(
  () => import("@/pages/npa/RequirementsPage"),
);
export const AuditPage = lazy(() => import("@/pages/audit/AuditPage"));
export const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage"));
export const ReportsPage = lazy(() => import("@/pages/reports/ReportsPage"));
export const ReportBuilderPage = lazy(
  () => import("@/pages/reports/ReportBuilderPage"),
);
export const ExecutiveDashboardPage = lazy(
  () => import("@/pages/dashboard/ExecutiveDashboardPage"),
);
export const SafetyDashboardPage = lazy(
  () => import("@/pages/dashboard/SafetyDashboardPage"),
);
export const TrainingDashboardPage = lazy(
  () => import("@/pages/dashboard/TrainingDashboardPage"),
);
export const PpeDashboardPage = lazy(
  () => import("@/pages/dashboard/PpeDashboardPage"),
);
export const ClientDeliveryDashboardPage = lazy(
  () => import("@/pages/dashboard/ClientDeliveryDashboardPage"),
);
export const TrendsPage = lazy(() => import("@/pages/analytics/TrendsPage"));
export const ManagementDashboardPage = lazy(
  () => import("@/pages/analytics/ManagementDashboardPage"),
);
export const ExportsPage = lazy(() => import("@/pages/exports/ExportsPage"));
export const ClientPortalDashboardPage = lazy(
  () => import("@/pages/client-portal/ClientPortalDashboardPage"),
);
export const ClientPortalPackagesPage = lazy(
  () => import("@/pages/client-portal/ClientPortalPackagesPage"),
);
export const ClientPortalDocumentsPage = lazy(
  () => import("@/pages/client-portal/ClientPortalDocumentsPage"),
);
export const ClientPortalHistoryPage = lazy(
  () => import("@/pages/client-portal/ClientPortalHistoryPage"),
);
export const ClientPortalRequestsPage = lazy(
  () => import("@/pages/client-portal/ClientPortalRequestsPage"),
);
export const PortalRequestsPage = lazy(
  () => import("@/pages/portal-requests/PortalRequestsPage"),
);
export const NotificationsPage = lazy(
  () => import("@/pages/notifications/NotificationsPage"),
);
export const CalendarPage = lazy(() => import("@/pages/calendar/CalendarPage"));
export const WarehousePage = lazy(
  () => import("@/pages/warehouse/WarehousePage"),
);
export const CrmFinancePage = lazy(
  () => import("@/pages/crm-finance/CrmFinancePage"),
);
export const IntegrationsPage = lazy(
  () => import("@/pages/integrations/IntegrationsPage"),
);
export const WorkflowPage = lazy(() => import("@/pages/workflow/WorkflowPage"));
export const WorkspaceAttentionPage = lazy(
  () => import("@/pages/workspace/WorkspaceAttentionPage"),
);
export const WorkspaceDataQualityPage = lazy(
  () => import("@/pages/workspace/WorkspaceDataQualityPage"),
);
export const SyncConflictHelpPage = lazy(
  () => import("@/pages/help/SyncConflictHelpPage"),
);
export const WorkPermitsPage = lazy(
  () => import("@/pages/work-permits/WorkPermitsPage"),
);
export const WorkPermitDetailPage = lazy(
  () => import("@/pages/work-permits/WorkPermitDetailPage"),
);
export const CommitteesPage = lazy(
  () => import("@/pages/committees/CommitteesPage"),
);
export const ClientCockpitPage = lazy(
  () => import("@/pages/managed-clients/ClientCockpitPage"),
);
export const ClientCardPage = lazy(
  () => import("@/pages/managed-clients/ClientCardPage"),
);
export const SignupPage = lazy(() => import("@/pages/auth/SignupPage"));
export const SitesPage = lazy(() => import("@/pages/sites/SitesPage"));
export const SiteCardPage = lazy(() => import("@/pages/sites/SiteCardPage"));
export const CommitteeKpiPage = lazy(
  () => import("@/pages/committees/CommitteeKpiPage"),
);
export const SoutPage = lazy(() => import("@/pages/sout/SoutPage"));
export const RulesPage = lazy(() => import("@/pages/rules/RulesPage"));
export const BudgetPage = lazy(() => import("@/pages/budget/BudgetPage"));
export const ImportsPage = lazy(() => import("@/pages/imports/ImportsPage"));
export * from "@/router/pageRegistry/documents";
export * from "@/router/pageRegistry/search";
