import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthLayout } from "@/layouts/AuthLayout";
import { MainLayout } from "@/layouts/MainLayout";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { useAuthStore } from "@/stores/auth";

const LoginPage = lazy(() => import("@/pages/auth/LoginPage"));
const DashboardPage = lazy(() => import("@/pages/dashboard/DashboardPage"));
const CompaniesPage = lazy(() => import("@/pages/companies/CompaniesPage"));
const PersonsPage = lazy(() => import("@/pages/persons/PersonsPage"));
const TemplatesPage = lazy(() => import("@/pages/templates/TemplatesPage"));
const PacksPage = lazy(() => import("@/pages/packs/PacksPage"));
const DocumentsPage = lazy(() => import("@/pages/documents/DocumentsPage"));
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
const NpaPage = lazy(() => import("@/pages/npa/NpaPage"));
const AuditPage = lazy(() => import("@/pages/audit/AuditPage"));
const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage"));

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
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/companies" element={<CompaniesPage />} />
              <Route path="/persons" element={<PersonsPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/packs" element={<PacksPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/files" element={<FilesPage />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/risk" element={<RiskPage />} />
              <Route path="/activities" element={<ActivitiesPage />} />
              <Route path="/ppe" element={<PpePage />} />
              <Route path="/training" element={<TrainingPage />} />
              <Route path="/medical" element={<MedicalPage />} />
              <Route path="/incidents" element={<IncidentsPage />} />
              <Route path="/inspections" element={<InspectionsPage />} />
              <Route path="/audit-prep" element={<AuditPrepPage />} />
              <Route path="/fire-safety" element={<FireSafetyPage />} />
              <Route path="/fire-training" element={<FireTrainingPage />} />
              <Route path="/fire-inspections" element={<FireInspectionsPage />} />
              <Route path="/reference" element={<ReferencePage />} />
              <Route path="/contractors" element={<ContractorsPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="/npa" element={<NpaPage />} />
              <Route path="/audit" element={<AuditPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/companies" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default AppRouter;
