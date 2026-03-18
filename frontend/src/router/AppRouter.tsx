import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthLayout } from "@/layouts/AuthLayout";
import { MainLayout } from "@/layouts/MainLayout";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { getLandingRoute } from "@/router/landing";
import { useAuthStore } from "@/stores/auth";

const LoginPage = lazy(() => import("@/pages/auth/LoginPage"));
const DashboardPage = lazy(() => import("@/pages/dashboard/DashboardPage"));
const CompaniesPage = lazy(() => import("@/pages/companies/CompaniesPage"));
const PersonsPage = lazy(() => import("@/pages/persons/PersonsPage"));
const TemplatesPage = lazy(() => import("@/pages/templates/TemplatesPage"));
const PacksPage = lazy(() => import("@/pages/packs/PacksPage"));
const DocumentsPage = lazy(() => import("@/pages/documents/DocumentsPage"));
const DocumentsWizardPage = lazy(() => import("@/pages/documents/DocumentsWizardPage"));
const FilesPage = lazy(() => import("@/pages/files/FilesPage"));
const TasksPage = lazy(() => import("@/pages/tasks/TasksPage"));
const RiskPage = lazy(() => import("@/pages/risk/RiskPage"));
const ActivitiesPage = lazy(() => import("@/pages/activities/ActivitiesPage"));
const PpePage = lazy(() => import("@/pages/ppe/PpePage"));
const TrainingPage = lazy(() => import("@/pages/training/TrainingPage"));
const BriefingsPage = lazy(() => import("@/pages/briefings/BriefingsPage"));
const MedicalPage = lazy(() => import("@/pages/medical/MedicalPage"));
const IncidentsPage = lazy(() => import("@/pages/incidents/IncidentsPage"));
const InspectionsPage = lazy(() => import("@/pages/inspections/InspectionsPage"));
const InspectionPlansPage = lazy(() => import("@/pages/inspection-plans/InspectionPlansPage"));
const InspectionChecklistsPage = lazy(() => import("@/pages/inspection-checklists/InspectionChecklistsPage"));
const FindingsPage = lazy(() => import("@/pages/findings/FindingsPage"));
const PrescriptionsPage = lazy(() => import("@/pages/prescriptions/PrescriptionsPage"));
const CorrectiveActionsPage = lazy(() => import("@/pages/corrective-actions/CorrectiveActionsPage"));
const InspectionPrepPackagesPage = lazy(() => import("@/pages/inspection-prep/InspectionPrepPackagesPage"));
const AuditPrepPage = lazy(() => import("@/pages/audit-prep/AuditPrepPage"));
const FireSafetyPage = lazy(() => import("@/pages/fire-safety/FireSafetyPage"));
const FireTrainingPage = lazy(() => import("@/pages/fire-training/FireTrainingPage"));
const FireInspectionsPage = lazy(() => import("@/pages/fire-inspections/FireInspectionsPage"));
const ReferencePage = lazy(() => import("@/pages/reference/ReferencePage"));
const ContractorsPage = lazy(() => import("@/pages/contractors/ContractorsPage"));
const AdminPage = lazy(() => import("@/pages/admin/AdminPage"));
const OutboxPage = lazy(() => import("@/pages/admin/OutboxPage"));
const BillingPage = lazy(() => import("@/pages/admin/BillingPage"));
const AdminLayoutPresetsPage = lazy(() => import("@/pages/AdminLayoutPresets/AdminLayoutPresetsPage"));
const NpaPage = lazy(() => import("@/pages/npa/NpaPage"));
const AuditPage = lazy(() => import("@/pages/audit/AuditPage"));
const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage"));
const ReportsPage = lazy(() => import("@/pages/reports/ReportsPage"));
const ApprovalsInboxPage = lazy(() => import("@/pages/approvals/ApprovalsInboxPage"));
const ApprovalsOutboxPage = lazy(() => import("@/pages/approvals/ApprovalsOutboxPage"));
const ApprovalRoutesPage = lazy(() => import("@/pages/approvals/ApprovalRoutesPage"));
const SignaturesPage = lazy(() => import("@/pages/signatures/SignaturesPage"));
const EdoPage = lazy(() => import("@/pages/edo/EdoPage"));
const PipelineRunsPage = lazy(() => import("@/pages/PipelineRuns"));
const PipelineRunDetailsPage = lazy(() => import("@/pages/PipelineRunDetails"));
const PipelineBuilderPage = lazy(() => import("@/pages/PipelineBuilderPage"));
const ArchiveSearchPage = lazy(() => import("@/pages/ArchiveSearch"));
const SearchPage = lazy(() => import("@/pages/SearchPage"));
const ExecutiveDashboardPage = lazy(() => import("@/pages/dashboard/ExecutiveDashboardPage"));
const SafetyDashboardPage = lazy(() => import("@/pages/dashboard/SafetyDashboardPage"));
const TrainingDashboardPage = lazy(() => import("@/pages/dashboard/TrainingDashboardPage"));
const PpeDashboardPage = lazy(() => import("@/pages/dashboard/PpeDashboardPage"));
const ClientDeliveryDashboardPage = lazy(() => import("@/pages/dashboard/ClientDeliveryDashboardPage"));
const TrendsPage = lazy(() => import("@/pages/analytics/TrendsPage"));
const ExportsPage = lazy(() => import("@/pages/exports/ExportsPage"));
const ClientPortalDashboardPage = lazy(() => import("@/pages/client-portal/ClientPortalDashboardPage"));
const ClientPortalPackagesPage = lazy(() => import("@/pages/client-portal/ClientPortalPackagesPage"));
const ClientPortalDocumentsPage = lazy(() => import("@/pages/client-portal/ClientPortalDocumentsPage"));
const ClientPortalHistoryPage = lazy(() => import("@/pages/client-portal/ClientPortalHistoryPage"));
const ClientPortalRequestsPage = lazy(() => import("@/pages/client-portal/ClientPortalRequestsPage"));
const PortalRequestsPage = lazy(() => import("@/pages/portal-requests/PortalRequestsPage"));
const NotificationsPage = lazy(() => import("@/pages/notifications/NotificationsPage"));
const CalendarPage = lazy(() => import("@/pages/calendar/CalendarPage"));
const PackageProfilesPage = lazy(() => import("@/pages/packs/PackageProfilesPage"));
const PackagePresetsPage = lazy(() => import("@/pages/packs/PackagePresetsPage"));
const GeneratePackWizardPage = lazy(() => import("@/pages/packs/GeneratePackWizardPage"));
const PackRunDetailsPage = lazy(() => import("@/pages/packs/PackRunDetailsPage"));
const WarehousePage = lazy(() => import("@/pages/warehouse/WarehousePage"));
const CrmFinancePage = lazy(() => import("@/pages/crm-finance/CrmFinancePage"));
const IntegrationsPage = lazy(() => import("@/pages/integrations/IntegrationsPage"));
const WorkflowPage = lazy(() => import("@/pages/workflow/WorkflowPage"));

const LandingRedirect = () => {
  const { can } = useAbility();
  return <Navigate to={getLandingRoute(can)} replace />;
};

const AppRouter = () => {
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    initialize().catch(() => undefined);
  }, [initialize]);

  return (
    <BrowserRouter>
      <Suspense fallback={<div className="flex min-h-screen items-center justify-center">Загрузка...</div>}>
        <Routes>
          <Route path="/auth" element={<AuthLayout />}>
            <Route path="login" element={<LoginPage />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route element={<MainLayout />}>
              <Route index element={<LandingRedirect />} />
              <Route path="/no-access" element={<AccessDeniedPage />} />
              <Route element={<ProtectedRoute permission={PERMISSIONS.DASHBOARD_VIEW} />}>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/dashboard/executive" element={<ExecutiveDashboardPage />} />
                <Route path="/dashboard/safety" element={<SafetyDashboardPage />} />
                <Route path="/dashboard/training" element={<TrainingDashboardPage />} />
                <Route path="/dashboard/ppe" element={<PpeDashboardPage />} />
                <Route path="/dashboard/client-delivery" element={<ClientDeliveryDashboardPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.COMPANY_VIEW} />}>
                <Route path="/companies" element={<CompaniesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.PERSON_VIEW} />}>
                <Route path="/persons" element={<PersonsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.TEMPLATE_VIEW} />}>
                <Route path="/templates" element={<TemplatesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.PACK_VIEW} />}>
                <Route path="/packs" element={<PacksPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.DOCUMENT_VIEW} />}>
                <Route path="/documents" element={<DocumentsPage />} />
                <Route path="/documents/wizard" element={<DocumentsWizardPage />} />
                <Route path="/generation" element={<DocumentsWizardPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.DOCUMENT_VIEW} />}>
                <Route path="/approvals/inbox" element={<ApprovalsInboxPage />} />
                <Route path="/approvals/outbox" element={<ApprovalsOutboxPage />} />
                <Route path="/approval-routes" element={<ApprovalRoutesPage />} />
                <Route path="/signatures" element={<SignaturesPage />} />
                <Route path="/edo" element={<EdoPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.FILE_VIEW} />}>
                <Route path="/files" element={<FilesPage />} />
                <Route path="/archive" element={<ArchiveSearchPage />} />
                <Route path="/archive/search" element={<ArchiveSearchPage />} />
                <Route path="/search" element={<SearchPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.TASK_VIEW} />}>
                <Route path="/tasks" element={<TasksPage />} />
                <Route path="/workflow" element={<WorkflowPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.TASK_VIEW} />}>
                <Route path="/notifications" element={<NotificationsPage />} />
                <Route path="/calendar" element={<CalendarPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.RISK_VIEW} />}>
                <Route path="/risk" element={<RiskPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.ACTIVITY_VIEW} />}>
                <Route path="/activities" element={<ActivitiesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.PPE_VIEW} />}>
                <Route path="/ppe" element={<PpePage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.WAREHOUSE_VIEW} />}>
                <Route path="/warehouse" element={<WarehousePage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.TRAINING_VIEW} />}>
                <Route path="/training" element={<TrainingPage />} />
                <Route path="/briefings" element={<BriefingsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.MEDICAL_VIEW} />}>
                <Route path="/medical" element={<MedicalPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.INCIDENT_VIEW} />}>
                <Route path="/incidents" element={<IncidentsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.INSPECTION_VIEW} />}>
                <Route path="/inspections" element={<InspectionsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.INSPECTION_VIEW} />}>
                <Route path="/inspection-plans" element={<InspectionPlansPage />} />
                <Route path="/inspection-checklists" element={<InspectionChecklistsPage />} />
                <Route path="/findings" element={<FindingsPage />} />
                <Route path="/prescriptions" element={<PrescriptionsPage />} />
                <Route path="/corrective-actions" element={<CorrectiveActionsPage />} />
                <Route path="/inspection-prep/packages" element={<InspectionPrepPackagesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.AUDIT_PREP_VIEW} />}>
                <Route path="/audit-prep" element={<AuditPrepPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.FIRE_SAFETY_VIEW} />}>
                <Route path="/fire-safety" element={<FireSafetyPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.FIRE_TRAINING_VIEW} />}>
                <Route path="/fire-training" element={<FireTrainingPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.FIRE_INSPECTIONS_VIEW} />}>
                <Route path="/fire-inspections" element={<FireInspectionsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.REFERENCE_VIEW} />}>
                <Route path="/reference" element={<ReferencePage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.CONTRACTOR_VIEW} />}>
                <Route path="/contractors" element={<ContractorsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.ADMIN_MANAGE_ROLES} />}>
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/admin/outbox" element={<OutboxPage />} />
                <Route path="/admin/billing" element={<BillingPage />} />
                <Route path="/admin/layout-presets" element={<AdminLayoutPresetsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.NPA_VIEW} />}>
                <Route path="/npa" element={<NpaPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.AUDIT_VIEW} />}>
                <Route path="/audit" element={<AuditPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.SETTINGS_VIEW} />}>
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.REPORTS_VIEW} />}>
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/exports" element={<ExportsPage />} />
                <Route path="/analytics/trends" element={<TrendsPage />} />
                <Route path="/portal-requests" element={<PortalRequestsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.CLIENT_PORTAL_VIEW} />}>
                <Route path="/client-portal/dashboard" element={<ClientPortalDashboardPage />} />
                <Route path="/client-portal/packages" element={<ClientPortalPackagesPage />} />
                <Route path="/client-portal/documents" element={<ClientPortalDocumentsPage />} />
                <Route path="/client-portal/history" element={<ClientPortalHistoryPage />} />
                <Route path="/client-portal/requests" element={<ClientPortalRequestsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.CRM_FINANCE_VIEW} />}>
                <Route path="/crm-finance" element={<CrmFinancePage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.INTEGRATIONS_VIEW} />}>
                <Route path="/integrations" element={<IntegrationsPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.DOCUMENT_VIEW} />}>
                <Route path="/pipelines/profiles" element={<PipelineBuilderPage />} />
                <Route path="/pipelines/runs" element={<PipelineRunsPage />} />
                <Route path="/pipelines/runs/:id" element={<PipelineRunDetailsPage />} />
                <Route path="/jobs" element={<PipelineRunsPage />} />
                <Route path="/jobs/:id" element={<PipelineRunDetailsPage />} />
                <Route path="/package-profiles" element={<PackageProfilesPage />} />
                <Route path="/package-presets" element={<PackagePresetsPage />} />
                <Route path="/generate-pack/:presetId" element={<GeneratePackWizardPage />} />
                <Route path="/pack-runs/:id" element={<PackRunDetailsPage />} />
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<LandingRedirect />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default AppRouter;
