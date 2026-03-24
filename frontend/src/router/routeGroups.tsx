import type { ReactElement } from "react";
import { Route } from "react-router-dom";

import { PERMISSIONS, type Permission } from "@/permissions/permissions";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import {
  ActivitiesPage,
  AdminLayoutPresetsPage,
  AdminPage,
  ApprovalRoutesPage,
  ApprovalsInboxPage,
  ApprovalsOutboxPage,
  ArchiveSearchPage,
  AuditPage,
  AuditPrepPage,
  BillingPage,
  BriefingsPage,
  BrandingSettingsPage,
  CalendarPage,
  ClientDeliveryDashboardPage,
  ClientPortalDashboardPage,
  ClientPortalDocumentsPage,
  ClientPortalHistoryPage,
  ClientPortalPackagesPage,
  ClientPortalRequestsPage,
  CompaniesPage,
  ContractorsPage,
  CorrectiveActionsPage,
  CrmFinancePage,
  DashboardPage,
  DocumentsPage,
  DocumentsWizardPage,
  EdoPage,
  ExecutiveDashboardPage,
  ExportsPage,
  FilesPage,
  FindingsPage,
  FireInspectionsPage,
  FireSafetyPage,
  FireTrainingPage,
  GeneratePackWizardPage,
  IncidentsPage,
  InspectionChecklistsPage,
  InspectionPlansPage,
  InspectionPrepPackagesPage,
  InspectionsPage,
  IntegrationsPage,
  MedicalPage,
  NotificationsPage,
  NpaPage,
  OutboxPage,
  PackagePresetsPage,
  PackageProfilesPage,
  PackRunDetailsPage,
  PacksPage,
  PersonsPage,
  PipelineBuilderPage,
  PipelineRunDetailsPage,
  PipelineRunsPage,
  PortalRequestsPage,
  PpeDashboardPage,
  PpePage,
  PrescriptionsPage,
  ReferencePage,
  ReportsPage,
  RiskPage,
  SafetyDashboardPage,
  SearchPage,
  SettingsPage,
  SignaturesPage,
  TasksPage,
  TemplatesPage,
  TrainingDashboardPage,
  TrainingPage,
  TrendsPage,
  WarehousePage,
  WorkflowPage
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
        <Route key="/dashboard/client-delivery" path="/dashboard/client-delivery" element={<ClientDeliveryDashboardPage />} />
      ]
    },
    { permission: PERMISSIONS.COMPANY_VIEW, routes: [<Route key="/companies" path="/companies" element={<CompaniesPage />} />] },
    { permission: PERMISSIONS.PERSON_VIEW, routes: [<Route key="/persons" path="/persons" element={<PersonsPage />} />] },
    { permission: PERMISSIONS.TEMPLATE_VIEW, routes: [<Route key="/templates" path="/templates" element={<TemplatesPage />} />] },
    { permission: PERMISSIONS.PACK_VIEW, routes: [<Route key="/packs" path="/packs" element={<PacksPage />} />] },
    {
      permission: PERMISSIONS.DOCUMENT_VIEW,
      routes: [
        <Route key="/documents" path="/documents" element={<DocumentsPage />} />,
        <Route key="/documents/branding" path="/documents/branding" element={<BrandingSettingsPage />} />,
        <Route key="/approvals/inbox" path="/approvals/inbox" element={<ApprovalsInboxPage />} />,
        <Route key="/approvals/outbox" path="/approvals/outbox" element={<ApprovalsOutboxPage />} />,
        <Route key="/approval-routes" path="/approval-routes" element={<ApprovalRoutesPage />} />,
        <Route key="/signatures" path="/signatures" element={<SignaturesPage />} />,
        <Route key="/edo" path="/edo" element={<EdoPage />} />,
        <Route key="/pipelines/profiles" path="/pipelines/profiles" element={<PipelineBuilderPage />} />,
        <Route key="/pipelines/runs" path="/pipelines/runs" element={<PipelineRunsPage />} />,
        <Route key="/pipelines/runs/:id" path="/pipelines/runs/:id" element={<PipelineRunDetailsPage />} />,
        <Route key="/jobs" path="/jobs" element={<PipelineRunsPage />} />,
        <Route key="/jobs/:id" path="/jobs/:id" element={<PipelineRunDetailsPage />} />,
        <Route key="/package-profiles" path="/package-profiles" element={<PackageProfilesPage />} />,
        <Route key="/package-presets" path="/package-presets" element={<PackagePresetsPage />} />,
        <Route key="/generate-pack/:presetId" path="/generate-pack/:presetId" element={<GeneratePackWizardPage />} />,
        <Route key="/pack-runs/:id" path="/pack-runs/:id" element={<PackRunDetailsPage />} />
      ]
    },
    {
      permission: PERMISSIONS.DOCUMENT_CREATE,
      routes: [
        <Route key="/documents/wizard" path="/documents/wizard" element={<DocumentsWizardPage />} />,
        <Route key="/generation" path="/generation" element={<DocumentsWizardPage />} />
      ]
    },
    {
      permission: PERMISSIONS.FILE_VIEW,
      routes: [
        <Route key="/files" path="/files" element={<FilesPage />} />,
        <Route key="/archive" path="/archive" element={<ArchiveSearchPage />} />,
        <Route key="/archive/search" path="/archive/search" element={<ArchiveSearchPage />} />,
        <Route key="/search" path="/search" element={<SearchPage />} />
      ]
    },
    {
      permission: PERMISSIONS.TASK_VIEW,
      routes: [
        <Route key="/tasks" path="/tasks" element={<TasksPage />} />,
        <Route key="/workflow" path="/workflow" element={<WorkflowPage />} />,
        <Route key="/notifications" path="/notifications" element={<NotificationsPage />} />,
        <Route key="/calendar" path="/calendar" element={<CalendarPage />} />
      ]
    },
    { permission: PERMISSIONS.RISK_VIEW, routes: [<Route key="/risk" path="/risk" element={<RiskPage />} />] },
    { permission: PERMISSIONS.ACTIVITY_VIEW, routes: [<Route key="/activities" path="/activities" element={<ActivitiesPage />} />] },
    { permission: PERMISSIONS.PPE_VIEW, routes: [<Route key="/ppe" path="/ppe" element={<PpePage />} />] },
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
    { permission: PERMISSIONS.AUDIT_PREP_VIEW, routes: [<Route key="/audit-prep" path="/audit-prep" element={<AuditPrepPage />} />] },
    { permission: PERMISSIONS.FIRE_SAFETY_VIEW, routes: [<Route key="/fire-safety" path="/fire-safety" element={<FireSafetyPage />} />] },
    { permission: PERMISSIONS.FIRE_TRAINING_VIEW, routes: [<Route key="/fire-training" path="/fire-training" element={<FireTrainingPage />} />] },
    { permission: PERMISSIONS.FIRE_INSPECTIONS_VIEW, routes: [<Route key="/fire-inspections" path="/fire-inspections" element={<FireInspectionsPage />} />] },
    { permission: PERMISSIONS.REFERENCE_VIEW, routes: [<Route key="/reference" path="/reference" element={<ReferencePage />} />] },
    { permission: PERMISSIONS.CONTRACTOR_VIEW, routes: [<Route key="/contractors" path="/contractors" element={<ContractorsPage />} />] },
    {
      permission: PERMISSIONS.ADMIN_MANAGE_ROLES,
      routes: [
        <Route key="/admin" path="/admin" element={<AdminPage />} />,
        <Route key="/admin/outbox" path="/admin/outbox" element={<OutboxPage />} />,
        <Route key="/admin/billing" path="/admin/billing" element={<BillingPage />} />,
        <Route key="/admin/layout-presets" path="/admin/layout-presets" element={<AdminLayoutPresetsPage />} />
      ]
    },
    { permission: PERMISSIONS.NPA_VIEW, routes: [<Route key="/npa" path="/npa" element={<NpaPage />} />] },
    { permission: PERMISSIONS.AUDIT_VIEW, routes: [<Route key="/audit" path="/audit" element={<AuditPage />} />] },
    { permission: PERMISSIONS.SETTINGS_VIEW, routes: [<Route key="/settings" path="/settings" element={<SettingsPage />} />] },
    {
      permission: PERMISSIONS.REPORTS_VIEW,
      routes: [
        <Route key="/reports" path="/reports" element={<ReportsPage />} />,
        <Route key="/exports" path="/exports" element={<ExportsPage />} />,
        <Route key="/analytics/trends" path="/analytics/trends" element={<TrendsPage />} />,
        <Route key="/portal-requests" path="/portal-requests" element={<PortalRequestsPage />} />
      ]
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
    { permission: PERMISSIONS.INTEGRATIONS_VIEW, routes: [<Route key="/integrations" path="/integrations" element={<IntegrationsPage />} />] }
  ];

  return groups.map(renderGuardedGroup);
};

