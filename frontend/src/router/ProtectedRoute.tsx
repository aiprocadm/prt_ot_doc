import { Navigate, Outlet, useLocation } from "react-router-dom";
import { shallow } from "zustand/shallow";

import { LoadingScreen } from "@/components/common/LoadingScreen";
import { useAbility } from "@/permissions/useAbility";
import { isRouteOfDisabledModule } from "@/router/navVisibility";
import { useAuthStore } from "@/stores/auth";
import { useModulesStore } from "@/stores/modules";
import type { AbilityResource } from "@/permissions/ability";
import type { Permission } from "@/permissions/permissions";

interface ProtectedRouteProps {
  permission?: Permission;
  resource?: AbilityResource;
}

export const ProtectedRoute = ({
  permission,
  resource,
}: ProtectedRouteProps) => {
  const location = useLocation();
  const [isAuthenticated, initialized] = useAuthStore(
    (state) => [state.isAuthenticated, state.initialized],
    shallow,
  );
  const { can } = useAbility();
  // Разд. 61.3, слой «роутинг»: спрятать пункт меню мало — заказчик,
  // знающий адрес, дошёл бы до экрана выключенного модуля и увидел пустую
  // страницу с невнятной ошибкой вместо ответа «модуль не подключён».
  const disabledRoutes = useModulesStore((state) => state.disabledRoutes);

  if (!initialized) {
    return <LoadingScreen label="Проверка сессии" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth/login" state={{ from: location }} replace />;
  }

  if (permission && !can(permission, resource)) {
    return <Navigate to="/no-access" state={{ from: location }} replace />;
  }

  // Порядок проверок из разд. 61.3: сначала арендатор и права, потом модуль.
  // Пустой список значит «скрывать нечего» (список ещё не загружен или запрос
  // не удался), а не «всё выключено»: настоящий запрет стоит на сервере, и
  // закрыть весь интерфейс из-за одного неудачного запроса — хуже.
  if (isRouteOfDisabledModule(location.pathname, disabledRoutes)) {
    return (
      <Navigate to="/module-unavailable" state={{ from: location }} replace />
    );
  }

  return <Outlet />;
};
