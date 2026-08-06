import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { getBillingSummary } from "@/api/billing";
import { useAbility } from "@/permissions/useAbility";
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
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    void getBillingSummary()
      .then((summary) => {
        if (cancelled) {
          return;
        }
        const next = summary.features ?? {};
        setFeatureFlags((prev) => {
          const pk = Object.keys(prev);
          const nk = Object.keys(next);
          if (pk.length === nk.length && pk.every((k) => prev[k] === next[k])) {
            return prev;
          }
          return next;
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const scopedGroups = clientPortalOnlyMode
    ? CLIENT_PORTAL_NAV_GROUPS
    : MAIN_NAV_GROUPS;

  const visibleGroups = useMemo(
    () => filterNavGroupsByAccess(scopedGroups, can, featureFlags),
    [scopedGroups, can, featureFlags],
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
