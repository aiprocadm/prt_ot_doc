import { useEffect, useMemo, useState } from "react";

import { getBillingSummary } from "@/api/billing";
import { useAbility } from "@/permissions/useAbility";
import { filterNavGroupsByAccess } from "@/router/navVisibility";
import { CLIENT_PORTAL_NAV_GROUPS, MAIN_NAV_GROUPS } from "@/router/navigationConfig";
import { useClientPortalOnlyMode } from "@/router/useNavScope";

export const useNavMenuData = () => {
  const { can } = useAbility();
  const clientPortalOnlyMode = useClientPortalOnlyMode();
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({});

  useEffect(() => {
    void getBillingSummary()
      .then((summary) => setFeatureFlags(summary.features ?? {}))
      .catch(() => undefined);
  }, []);

  const scopedGroups = clientPortalOnlyMode ? CLIENT_PORTAL_NAV_GROUPS : MAIN_NAV_GROUPS;

  const visibleGroups = useMemo(
    () => filterNavGroupsByAccess(scopedGroups, can, featureFlags),
    [scopedGroups, can, featureFlags]
  );

  return { visibleGroups, clientPortalOnlyMode };
};
