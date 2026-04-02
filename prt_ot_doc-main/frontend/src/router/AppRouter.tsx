import { Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthLayout } from "@/layouts/AuthLayout";
import { MainLayout } from "@/layouts/MainLayout";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { buildProtectedRouteGroups } from "@/router/routeGroups";
import { LoginPage } from "@/router/pageRegistry";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { getLandingRoute } from "@/router/landing";
import { useAbility } from "@/permissions/useAbility";
import { useAuthStore } from "@/stores/auth";

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
              {buildProtectedRouteGroups()}
            </Route>
          </Route>
          <Route path="*" element={<LandingRedirect />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default AppRouter;
