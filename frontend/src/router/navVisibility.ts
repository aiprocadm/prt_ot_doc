import type { Permission } from "@/permissions/permissions";

import type { NavGroup } from "@/router/navigationConfig";

export function filterNavGroupsByAccess(
  groups: NavGroup[],
  can: (permission: Permission) => boolean,
  featureFlags: Record<string, boolean>
): NavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (item.to === "/edo" && featureFlags.edo === false) return false;
        if (item.to === "/committees" && featureFlags.committees === false) return false;
        if (item.to === "/sout" && featureFlags.sout === false) return false;
        if (item.to === "/rules" && featureFlags.rules_engine === false) return false;
        return can(item.permission);
      })
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
        groupTitle: group.title
      });
    }
  }
  return out;
}

export function matchesNavCommandQuery(item: FlatNavCommandItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return item.label.toLowerCase().includes(q) || item.groupTitle.toLowerCase().includes(q);
}
