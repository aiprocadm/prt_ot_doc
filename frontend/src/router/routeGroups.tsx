import type { ReactElement } from "react";
import { Route } from "react-router-dom";

import { PERMISSIONS, type Permission } from "@/permissions/permissions";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { documentCreateRoutes, documentReadRoutes } from "@/router/features/documentRoutes";
import { searchAndFilesRoutes } from "@/router/features/searchAndFilesRoutes";
import {
  ActivitiesPage,
  CommitteesPage,
  SoutPage,
  AdminLayoutPresetsPage,
  AdminPage,
  AuditPage,
  AuditPrepPage,
  BillingPage,
  BriefingsPage,
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
  OutboxPage,
  PacksPage,
  PersonsPage,
  PortalRequestsPage,
  PpeDashboardPage,
  PpePage,
  PermitsPage,
  PrescriptionsPage,
  ReferencePage,
  ReportBuilderPage,
  ReportsPage,
  RiskPage,
  SafetyDashboardPage,
  SettingsPage,
  SyncConflictHelpPage,
  TasksPage,
  TemplatesPage,
  TrainingDashboardPage,
  TrainingPage,
  TrendsPage,
  WarehousePage,
  WorkflowPage,
  WorkPermitDetailPage,
  WorkPermitsPage,
  WorkspaceAttentionPage,
  WorkspaceDataQualityPage
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
        <Route key="/dashboard" path="/dashboard" element={<DashboardPage />} />,
        <Route key="/dashboard/executive" path="/dashboard/executive" element={<ExecutiveDashboardPage />} />,
        <Route key="/dashboard/safety" path="/dashboard/safety" element={<SafetyDashboardPage />} />,
        <Route key="/dashboard/training" path="/dashboard/training" element={<TrainingDashboardPage />} />,
        <Route key="/dashboard/ppe" path="/dashboard/ppe" element={<PpeDashboardPage />} />,
        <Route key="/dashboard/client-delivery" path="/dashboard/client-delivery" element={<ClientDeliveryDashboardPage />} />,
        <Route key="/command-center" path="/command-center" element={<CommandCenterPage />} />,
        <Route key="/workspace/attention" path="/workspace/attention" element={<WorkspaceAttentionPage />} />
      ]
    },
    {
      permission: PERMISSIONS.DATA_QUALITY_VIEW,
      routes: [
        <Route key="/workspace/data-quality" path="/workspace/data-quality" element={<WorkspaceDataQualityPage />} />
      ]
    },
    { permission: PERMISSIONS.COMPANY_VIEW, routes: [<Route key="/companies" path="/companies" element={<CompaniesPage />} />] },
    { permission: PERMISSIONS.BRANCH_VIEW, routes: [<Route key="/branches" path="/branches" element={<BranchesPage />} />] },
    { permission: PERMISSIONS.PERSON_VIEW, routes: [<Route key="/persons" path="/persons" element={<PersonsPage />} />] },
    {
      permission: PERMISSIONS.EMPLOYEE_CARD_VIEW,
      routes: [
        <Route key="/employees/:personId" path="/employees/:personId" element={<EmployeeCardPage />} />
      ]
    },
    { permission: PERMISSIONS.TEMPLATE_VIEW, routes: [<Route key="/templates" path="/templates" element={<TemplatesPage />} />] },
    { permission: PERMISSIONS.PACK_VIEW, routes: [<Route key="/packs" path="/packs" element={<PacksPage />} />] },
    {
      permission: PERMISSIONS.DOCUMENT_VIEW,
      routes: documentReadRoutes()
    },
    {
      permission: PERMISSIONS.DOCUMENT_CREATE,
      routes: documentCreateRoutes()
    },
    {
      permission: PERMISSIONS.FILE_VIEW,
      routes: searchAndFilesRoutes()
    },
    {
      permission: PERMISSIONS.TASK_VIEW,
      routes: [
        <Route key="/tasks" path="/tasks" element={<TasksPage />} />,
        <Route key="/workflow" path="/workflow" element={<WorkflowPage />} />,
        <Route key="/notifications" path="/notifications" element={<NotificationsPage />} />
      ]
    },
    {
      permission: PERMISSIONS.CALENDAR_VIEW,
      routes: [<Route key="/calendar" path="/calendar" element={<CalendarPage />} />]
    },
    { permission: PERMISSIONS.RISK_VIEW, routes: [<Route key="/risk" path="/risk" element={<RiskPage />} />] },
    { permission: PERMISSIONS.ACTIVITY_VIEW, routes: [<Route key="/activities" path="/activities" element={<ActivitiesPage />} />] },
    { permission: PERMISSIONS.PPE_VIEW, routes: [<Route key="/ppe" path="/ppe" element={<PpePage />} />] },
    { permission: PERMISSIONS.PPE_ISSUE, routes: [<Route key="/ppe/issue" path="/ppe/issue" element={<MobileIssuePage />} />] },
    { permission: PERMISSIONS.WAREHOUSE_VIEW, routes: [<Route key="/warehouse" path="/warehouse" element={<WarehousePage />} />] },
    {
      permission: PERMISSIONS.TRAINING_VIEW,
      routes: [
        <Route key="/training" path="/training" element={<TrainingPage />} />,
        <Route key="/briefings" path="/briefings" element={<BriefingsPage />} />
      ]
    },
    { permission: PERMISSIONS.MEDICAL_VIEW, routes: [<Route key="/medical" path="/medical" element={<MedicalPage />} />] },
    { permission: PERMISSIONS.INCIDENT_VIEW, routes: [<Route key="/incidents" path="/incidents" element={<IncidentsPage />} />] },
    {
      permission: PERMISSIONS.INSPECTION_VIEW,
      routes: [
        <Route key="/inspections" path="/inspections" element={<InspectionsPage />} />,
        <Route key="/inspection-plans" path="/inspection-plans" element={<InspectionPlansPage />} />,
        <Route key="/inspection-checklists" path="/inspection-checklists" element={<InspectionChecklistsPage />} />,
        <Route key="/findings" path="/findings" element={<FindingsPage />} />,
        <Route key="/prescriptions" path="/prescriptions" element={<PrescriptionsPage />} />,
        <Route key="/corrective-actions" path="/corrective-actions" element={<CorrectiveActionsPage />} />,
        <Route key="/inspection-prep/packages" path="/inspection-prep/packages" element={<InspectionPrepPackagesPage />} />
      ]
    },
    {
      permission: PERMISSIONS.PERMIT_VIEW,
      routes: [<Route key="/permits" path="/permits" element={<PermitsPage />} />]
    },
    { permission: PERMISSIONS.AUDIT_PREP_VIEW, routes: [<Route key="/audit-prep" path="/audit-prep" element={<AuditPrepPage />} />] },
    { permission: PERMISSIONS.FIRE_SAFETY_VIEW, routes: [<Route key="/fire-safety" path="/fire-safety" element={<FireSafetyPage />} />] },
    { permission: PERMISSIONS.FIRE_TRAINING_VIEW, routes: [<Route key="/fire-training" path="/fire-training" element={<FireTrainingPage />} />] },
    { permission: PERMISSIONS.FIRE_INSPECTIONS_VIEW, routes: [<Route key="/fire-inspections" path="/fire-inspections" element={<FireInspectionsPage />} />] },
    { permission: PERMISSIONS.REFERENCE_VIEW, routes: [<Route key="/reference" path="/reference" element={<ReferencePage />} />] },
    {
      permission: PERMISSIONS.CONTRACTOR_VIEW,
      routes: [
        <Route key="/contractors" path="/contractors" element={<ContractorsPage />} />,
        <Route key="/contractors/:id" path="/contractors/:id" element={<ContractorDetailPage />} />
      ]
    },
    {
      permission: PERMISSIONS.WORK_PERMIT_VIEW,
      routes: [
        <Route key="/work-permits" path="/work-permits" element={<WorkPermitsPage />} />,
        <Route key="/work-permits/:id" path="/work-permits/:id" element={<WorkPermitDetailPage />} />
      ]
    },
    {
      permission: PERMISSIONS.ADMIN_MANAGE_ROLES,
      routes: [
        <Route key="/admin" path="/admin" element={<AdminPage />} />,
        <Route key="/admin/outbox" path="/admin/outbox" element={<OutboxPage />} />,
        <Route key="/admin/health" path="/admin/health" element={<HealthStatusPage />} />,
        <Route key="/admin/billing" path="/admin/billing" element={<BillingPage />} />,
        <Route key="/admin/layout-presets" path="/admin/layout-presets" element={<AdminLayoutPresetsPage />} />
      ]
    },
    { permission: PERMISSIONS.NPA_VIEW, routes: [<Route key="/npa" path="/npa" element={<NpaPage />} />] },
    { permission: PERMISSIONS.AUDIT_VIEW, routes: [<Route key="/audit" path="/audit" element={<AuditPage />} />] },
    {
      permission: PERMISSIONS.SETTINGS_VIEW,
      routes: [
        <Route key="/settings" path="/settings" element={<SettingsPage />} />,
        <Route key="/help/sync-conflicts" path="/help/sync-conflicts" element={<SyncConflictHelpPage />} />
      ]
    },
    {
      permission: PERMISSIONS.REPORTS_VIEW,
      routes: [
        <Route key="/reports" path="/reports" element={<ReportsPage />} />,
        <Route key="/reports/builder" path="/reports/builder" element={<ReportBuilderPage />} />,
        <Route key="/exports" path="/exports" element={<ExportsPage />} />,
        <Route key="/analytics/trends" path="/analytics/trends" element={<TrendsPage />} />,
        <Route key="/portal-requests" path="/portal-requests" element={<PortalRequestsPage />} />
      ]
    },
    {
      permission: PERMISSIONS.ANALYTICS_VIEW,
      routes: [<Route key="/analytics" path="/analytics" element={<ManagementDashboardPage />} />]
    },
    {
      permission: PERMISSIONS.CLIENT_PORTAL_VIEW,
      routes: [
        <Route key="/client-portal/dashboard" path="/client-portal/dashboard" element={<ClientPortalDashboardPage />} />,
        <Route key="/client-portal/packages" path="/client-portal/packages" element={<ClientPortalPackagesPage />} />,
        <Route key="/client-portal/documents" path="/client-portal/documents" element={<ClientPortalDocumentsPage />} />,
        <Route key="/client-portal/history" path="/client-portal/history" element={<ClientPortalHistoryPage />} />,
        <Route key="/client-portal/requests" path="/client-portal/requests" element={<ClientPortalRequestsPage />} />
      ]
    },
    { permission: PERMISSIONS.CRM_FINANCE_VIEW, routes: [<Route key="/crm-finance" path="/crm-finance" element={<CrmFinancePage />} />] },
    { permission: PERMISSIONS.INTEGRATIONS_VIEW, routes: [<Route key="/integrations" path="/integrations" element={<IntegrationsPage />} />] },
    { permission: PERMISSIONS.COMMITTEE_VIEW, routes: [<Route key="/committees" path="/committees" element={<CommitteesPage />} />] },
    { permission: PERMISSIONS.SOUT_VIEW, routes: [<Route key="/sout" path="/sout" element={<SoutPage />} />] }
  ];

  return groups.map(renderGuardedGroup);
};

