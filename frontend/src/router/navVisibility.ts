import type { Permission } from "@/permissions/permissions";

import type { NavGroup } from "@/router/navigationConfig";

/**
 * Маршруты выключенных модулей (BIZ-61 срез-5, разд. 61.3).
 *
 * Приходят с сервера (`/tenants/me/modules`). Пустой набор значит «скрывать
 * нечего», а не «всё выключено»: настоящий запрет стоит на сервере, и прятать
 * всё меню из-за неудачного запроса — хуже, чем показать лишний пункт.
 */
export type DisabledModuleRoutes = string[];

/** Принадлежит ли экран ``path`` выключенному модулю. */
export function isRouteOfDisabledModule(
  path: string,
  disabledRoutes: DisabledModuleRoutes,
): boolean {
  return disabledRoutes.some(
    // Префикс, а не точное совпадение: вложенные экраны («/committees/kpi»)
    // принадлежат тому же модулю и обязаны исчезать вместе с ним.
    (route) => path === route || path.startsWith(`${route}/`),
  );
}

export function filterNavGroupsByAccess(
  groups: NavGroup[],
  can: (permission: Permission) => boolean,
  disabledRoutes: DisabledModuleRoutes,
): NavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (isRouteOfDisabledModule(item.to, disabledRoutes)) return false;
        return can(item.permission);
      }),
    }))
    .filter((group) => group.items.length > 0);
}

export type FlatNavCommandItem = {
  id: string;
  label: string;
  path: string;
  groupTitle: string;
};

export function flattenNavGroups(groups: NavGroup[]): FlatNavCommandItem[] {
  const out: FlatNavCommandItem[] = [];
  for (const group of groups) {
    for (const item of group.items) {
      out.push({
        id: `${group.title}::${item.to}`,
        label: item.label,
        path: item.to,
        groupTitle: group.title,
      });
    }
  }
  return out;
}

export function matchesNavCommandQuery(
  item: FlatNavCommandItem,
  query: string,
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    item.label.toLowerCase().includes(q) ||
    item.groupTitle.toLowerCase().includes(q)
  );
}
