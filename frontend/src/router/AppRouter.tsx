import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthLayout } from "@/layouts/AuthLayout";
import { MainLayout } from "@/layouts/MainLayout";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { ProtectedRoute } from "@/router/ProtectedRoute";
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
const MedicalPage = lazy(() => import("@/pages/medical/MedicalPage"));
const IncidentsPage = lazy(() => import("@/pages/incidents/IncidentsPage"));
const InspectionsPage = lazy(() => import("@/pages/inspections/InspectionsPage"));
const AuditPrepPage = lazy(() => import("@/pages/audit-prep/AuditPrepPage"));
const FireSafetyPage = lazy(() => import("@/pages/fire-safety/FireSafetyPage"));
const FireTrainingPage = lazy(() => import("@/pages/fire-training/FireTrainingPage"));
const FireInspectionsPage = lazy(() => import("@/pages/fire-inspections/FireInspectionsPage"));
const ReferencePage = lazy(() => import("@/pages/reference/ReferencePage"));
const ContractorsPage = lazy(() => import("@/pages/contractors/ContractorsPage"));
const AdminPage = lazy(() => import("@/pages/admin/AdminPage"));
const OutboxPage = lazy(() => import("@/pages/admin/OutboxPage"));
const NpaPage = lazy(() => import("@/pages/npa/NpaPage"));
const AuditPage = lazy(() => import("@/pages/audit/AuditPage"));
const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage"));
const ReportsPage = lazy(() => import("@/pages/reports/ReportsPage"));

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
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="/no-access" element={<AccessDeniedPage />} />
              <Route element={<ProtectedRoute permission={PERMISSIONS.DASHBOARD_VIEW} />}>
                <Route path="/dashboard" element={<DashboardPage />} />
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
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.FILE_VIEW} />}>
                <Route path="/files" element={<FilesPage />} />
              </Route>
              <Route element={<ProtectedRoute permission={PERMISSIONS.TASK_VIEW} />}>
                <Route path="/tasks" element={<TasksPage />} />
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
              <Route element={<ProtectedRoute permission={PERMISSIONS.TRAINING_VIEW} />}>
                <Route path="/training" element={<TrainingPage />} />
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
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/companies" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default AppRouter;
