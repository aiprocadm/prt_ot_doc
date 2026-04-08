import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { Building2 } from "lucide-react";

import { PERMISSIONS } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";
import { getBillingSummary } from "@/api/billing";
import { CLIENT_PORTAL_NAV_GROUPS, MAIN_NAV_GROUPS } from "@/router/navigationConfig";

export const SideNav = () => {
  const { can } = useAbility();
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({});

  const clientPortalOnlyMode =
    can(PERMISSIONS.CLIENT_PORTAL_VIEW) &&
    ![
      PERMISSIONS.DASHBOARD_VIEW,
      PERMISSIONS.COMPANY_VIEW,
      PERMISSIONS.DOCUMENT_VIEW,
      PERMISSIONS.PACK_VIEW,
      PERMISSIONS.TASK_VIEW,
      PERMISSIONS.REPORTS_VIEW,
      PERMISSIONS.ADMIN_MANAGE_ROLES
    ].some((permission) => can(permission));

  useEffect(() => {
    void getBillingSummary()
      .then((summary) => setFeatureFlags(summary.features ?? {}))
      .catch(() => undefined);
  }, []);

  const scopedGroups = clientPortalOnlyMode ? CLIENT_PORTAL_NAV_GROUPS : MAIN_NAV_GROUPS;

  const visibleGroups = scopedGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (item.to === "/edo" && featureFlags.edo === false) return false;
        return can(item.permission);
      })
    }))
    .filter((group) => group.items.length > 0);

  return (
    <aside className="hidden h-[calc(100vh-4rem)] w-72 flex-shrink-0 border-r bg-background/95 px-4 py-6 lg:sticky lg:top-16 lg:block">
      <div className="flex items-center gap-2 text-lg font-semibold">
        <Building2 className="h-5 w-5 text-primary" />
        {clientPortalOnlyMode ? "Кабинет клиента" : "OT/ПБ Контур"}
      </div>
      <nav className="mt-6 space-y-6 text-sm">
        {visibleGroups.map((group) => (
          <div key={group.title} className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.title}</div>
            <div className="space-y-1">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-md px-3 py-2 transition-colors ${
                      isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                    }`
                  }
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
};
