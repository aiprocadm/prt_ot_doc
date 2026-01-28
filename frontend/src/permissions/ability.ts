import type { UserDto } from "@/types/dto/auth";

import { ALL_PERMISSIONS, PERMISSIONS, ROLE_PERMISSIONS, type Permission, type Role } from "@/permissions/permissions";

export interface AbilityResource {
  tenant_id?: string;
  company_id?: string;
  site_id?: string;
  status?: string;
  risk_level?: string;
  template?: {
    current_version?: { id?: string; status?: string };
  };
  version?: {
    id?: string;
    status?: string;
  };
}

export interface AbilityResult {
  can: (permission: Permission, resource?: AbilityResource) => boolean;
  permissions: Set<Permission>;
}

const normalizeRole = (role: string): Role | null => {
  const normalized = role.trim().toLowerCase().replace(/[\s/]+/g, "_");
  return normalized in ROLE_PERMISSIONS ? (normalized as Role) : null;
};

const resolvePermissions = (user: UserDto | null): Set<Permission> => {
  if (!user) return new Set();
  if (user.permissions?.length) {
    return new Set(user.permissions.filter((permission): permission is Permission => ALL_PERMISSIONS.includes(permission as Permission)));
  }
  const permissions = new Set<Permission>();
  user.roles.forEach((role) => {
    const normalized = normalizeRole(role);
    if (!normalized) return;
    ROLE_PERMISSIONS[normalized].forEach((permission) => permissions.add(permission));
  });
  return permissions;
};

const isAdminUser = (user: UserDto | null) => {
  if (!user) return false;
  if (user.attributes?.is_admin) return true;
  return user.roles.some((role) => ["admin", "owner"].includes(role.toLowerCase()));
};

const matchesScope = (user: UserDto, resource?: AbilityResource) => {
  if (!resource) return true;
  const { tenant_id, company_id, site_id } = resource;
  if (tenant_id && user.attributes?.tenant_id && tenant_id !== user.attributes.tenant_id) return false;
  if (company_id && user.attributes?.company_ids?.length && !user.attributes.company_ids.includes(company_id)) return false;
  if (site_id && user.attributes?.site_ids?.length && !user.attributes.site_ids.includes(site_id)) return false;
  return true;
};

const ABAC_RULES: Partial<Record<Permission, (user: UserDto, resource?: AbilityResource) => boolean>> = {
  [PERMISSIONS.DOCUMENT_SIGN]: (_user, resource) => ["ready"].includes(resource?.status ?? ""),
  [PERMISSIONS.DOCUMENT_EXPORT]: (_user, resource) => ["ready"].includes(resource?.status ?? ""),
  [PERMISSIONS.RISK_EXPORT]: (_user, resource) => ["approved"].includes(resource?.status ?? ""),
  [PERMISSIONS.RISK_EDIT]: (_user, resource) => resource?.risk_level ? resource.risk_level !== "high" : true,
  [PERMISSIONS.TEMPLATE_EDIT]: (_user, resource) => resource?.template?.current_version?.status !== "published",
  [PERMISSIONS.TEMPLATE_ACTIVATE]: (_user, resource) => {
    if (!resource?.version) return false;
    if (resource.version.status !== "published") return false;
    return resource.template?.current_version?.id !== resource.version.id;
  }
};

export const buildAbility = (user: UserDto | null): AbilityResult => {
  const permissions = resolvePermissions(user);
  const can = (permission: Permission, resource?: AbilityResource) => {
    if (!user) return false;
    if (isAdminUser(user)) return true;
    if (!permissions.has(permission)) return false;
    if (!matchesScope(user, resource)) return false;
    const abacRule = ABAC_RULES[permission];
    if (abacRule) return abacRule(user, resource);
    return true;
  };

  return { can, permissions };
};
