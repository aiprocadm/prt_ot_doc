import { Suspense, useEffect, useRef, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import { AuthLayout } from "@/layouts/AuthLayout";
import { MainLayout } from "@/layouts/MainLayout";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { AuthRedirectHandler } from "@/router/AuthRedirectHandler";
import { buildProtectedRouteGroups } from "@/router/routeGroups";
import { LoginPage } from "@/router/pageRegistry";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { getLandingRoute } from "@/router/landing";
import { useAbility } from "@/permissions/useAbility";
import { useAuthStore } from "@/stores/auth";
import { trackUxMetric } from "@/utils/uxMetrics";

const LandingRedirect = () => {
  const { can } = useAbility();
  const [landingRoute, setLandingRoute] = useState<string | null>(null);

  useEffect(() => {
    getLandingRoute(can).then(setLandingRoute);
  }, [can]);

  if (!landingRoute) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        Загрузка...
      </div>
    );
  }

  return <Navigate to={landingRoute} replace />;
};

const RouteMetricsTracker = () => {
  const location = useLocation();
  const previousPathRef = useRef<string | null>(null);

  useEffect(() => {
    const currentPath = `${location.pathname}${location.search}`;
    trackUxMetric("route_view", { path: currentPath });
    const previousPath = previousPathRef.current;
    if (previousPath) {
      trackUxMetric("nav_backtrack_rate", {
        from: previousPath,
        to: currentPath,
        is_backtrack: currentPath === previousPath ? 1 : 0,
      });
    }
    previousPathRef.current = currentPath;
  }, [location.pathname, location.search]);

  return null;
};

const AppRouter = () => {
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    initialize().catch(() => undefined);
  }, [initialize]);

  return (
    <BrowserRouter>
      <RouteMetricsTracker />
      <AuthRedirectHandler />
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center">
            Загрузка...
          </div>
        }
      >
        <Routes>
          <Route path="/auth" element={<AuthLayout />}>
            <Route path="login" element={<LoginPage />} />
          </Route>
          <Route path="/no-access" element={<AccessDeniedPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<MainLayout />}>
              <Route index element={<LandingRedirect />} />
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
