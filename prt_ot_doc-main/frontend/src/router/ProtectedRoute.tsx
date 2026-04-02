import { Navigate, Outlet, useLocation } from "react-router-dom";
import { shallow } from "zustand/shallow";

import { LoadingScreen } from "@/components/common/LoadingScreen";
import { useAbility } from "@/permissions/useAbility";
import { useAuthStore } from "@/stores/auth";
import type { AbilityResource } from "@/permissions/ability";
import type { Permission } from "@/permissions/permissions";

interface ProtectedRouteProps {
  permission?: Permission;
  resource?: AbilityResource;
}

export const ProtectedRoute = ({ permission, resource }: ProtectedRouteProps) => {
  const location = useLocation();
  const [isAuthenticated, initialized] = useAuthStore(
    (state) => [state.isAuthenticated, state.initialized],
    shallow
  );
  const { can } = useAbility();

  if (!initialized) {
    return <LoadingScreen label="Проверка сессии" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth/login" state={{ from: location }} replace />;
  }

  if (permission && !can(permission, resource)) {
    return <Navigate to="/no-access" state={{ from: location }} replace />;
  }

  return <Outlet />;
};
