import { NavLink } from "react-router-dom";
import { Building2 } from "lucide-react";

import { useNavMenuData } from "@/hooks/useNavMenuData";

const FREQUENT_PATHS = ["/dashboard", "/documents", "/tasks", "/packs", "/persons"];

export const SideNav = () => {
  const { visibleGroups, clientPortalOnlyMode } = useNavMenuData();
  const frequentItems = visibleGroups
    .flatMap((group) => group.items)
    .filter((item) => FREQUENT_PATHS.includes(item.to));
  const otherGroups = visibleGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !FREQUENT_PATHS.includes(item.to))
    }))
    .filter((group) => group.items.length > 0);

  return (
    <aside className="hidden h-[calc(100vh-4rem)] w-72 flex-shrink-0 border-r bg-background/95 px-4 py-6 lg:sticky lg:top-16 lg:block">
      <div className="flex items-center gap-2 text-lg font-semibold">
        <Building2 className="h-5 w-5 text-primary" />
        {clientPortalOnlyMode ? "Кабинет клиента" : "OT/ПБ Контур"}
      </div>
      <nav className="mt-6 space-y-6 text-sm">
        {frequentItems.length ? (
          <div className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Часто</div>
            <div className="space-y-1">
              {frequentItems.map((item) => (
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
        ) : null}
        {otherGroups.map((group) => (
          <div key={group.title} className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Остальное · {group.title}</div>
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
