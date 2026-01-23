import { Navigate, Outlet, useLocation } from "react-router-dom";
import { shallow } from "zustand/shallow";

import { LoadingScreen } from "@/components/common/LoadingScreen";
import { useAuthStore } from "@/stores/auth";

export const ProtectedRoute = () => {
  const location = useLocation();
  const [isAuthenticated, initialized] = useAuthStore(
    (state) => [state.isAuthenticated, state.initialized],
    shallow
  );

  if (!initialized) {
    return <LoadingScreen label="Проверка сессии" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
};
