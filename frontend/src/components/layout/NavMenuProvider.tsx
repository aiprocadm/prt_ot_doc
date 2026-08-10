import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";

import { useAbility } from "@/permissions/useAbility";
import { useModulesStore } from "@/stores/modules";
import { filterNavGroupsByAccess } from "@/router/navVisibility";
import {
  CLIENT_PORTAL_NAV_GROUPS,
  MAIN_NAV_GROUPS,
  type NavGroup,
} from "@/router/navigationConfig";
import { useClientPortalOnlyMode } from "@/router/useNavScope";

export type NavMenuContextValue = {
  visibleGroups: NavGroup[];
  clientPortalOnlyMode: boolean;
};

const NavMenuContext = createContext<NavMenuContextValue | undefined>(
  undefined,
);

export const NavMenuProvider = ({ children }: { children: ReactNode }) => {
  const { can } = useAbility();
  const clientPortalOnlyMode = useClientPortalOnlyMode();
  // Раньше признаки брались из `/billing/plan` — это фичи ТАРИФА БИЛЛИНГА, а
  // фактическая выдача модуля живёт в другом хранилище. Они расходятся, и
  // клиент видел пункт меню модуля, которого у него нет. Плюс та ручка
  // закрыта ролью owner/admin: у рядового пользователя признаки всегда были
  // пустыми, и не скрывалось ничего.
  const disabledRoutes = useModulesStore((state) => state.disabledRoutes);
  const loadModules = useModulesStore((state) => state.load);

  useEffect(() => {
    void loadModules();
  }, [loadModules]);

  const scopedGroups = clientPortalOnlyMode
    ? CLIENT_PORTAL_NAV_GROUPS
    : MAIN_NAV_GROUPS;

  const visibleGroups = useMemo(
    () => filterNavGroupsByAccess(scopedGroups, can, disabledRoutes),
    [scopedGroups, can, disabledRoutes],
  );

  const value = useMemo(
    () => ({ visibleGroups, clientPortalOnlyMode }),
    [visibleGroups, clientPortalOnlyMode],
  );

  return (
    <NavMenuContext.Provider value={value}>{children}</NavMenuContext.Provider>
  );
};

export const useNavMenuData = (): NavMenuContextValue => {
  const ctx = useContext(NavMenuContext);
  if (!ctx) {
    throw new Error("useNavMenuData must be used within NavMenuProvider");
  }
  return ctx;
};
