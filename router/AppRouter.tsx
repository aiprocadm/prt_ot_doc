import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthLayout } from "@/layouts/AuthLayout";
import { MainLayout } from "@/layouts/MainLayout";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { useAuthStore } from "@/stores/auth";

const LoginPage = lazy(() => import("@/pages/auth/LoginPage"));
const CompaniesPage = lazy(() => import("@/pages/companies/CompaniesPage"));
const PersonsPage = lazy(() => import("@/pages/persons/PersonsPage"));
const TemplatesPage = lazy(() => import("@/pages/templates/TemplatesPage"));
const PacksPage = lazy(() => import("@/pages/packs/PacksPage"));
const DocumentsPage = lazy(() => import("@/pages/documents/DocumentsPage"));
const FilesPage = lazy(() => import("@/pages/files/FilesPage"));
const TasksPage = lazy(() => import("@/pages/tasks/TasksPage"));
const RiskPage = lazy(() => import("@/pages/risk/RiskPage"));
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
              <Route index element={<Navigate to="/companies" replace />} />
              <Route path="/companies" element={<CompaniesPage />} />
              <Route path="/persons" element={<PersonsPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/packs" element={<PacksPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/files" element={<FilesPage />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/risk" element={<RiskPage />} />
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
