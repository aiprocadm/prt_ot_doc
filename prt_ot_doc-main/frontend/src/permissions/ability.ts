import type { UserDto } from "@/types/dto/auth";

import { ALL_PERMISSIONS, PERMISSIONS, ROLE_PERMISSIONS, type Permission, type Role } from "@/permissions/permissions";

export interface AbilityResource {
  tenant_id?: string;
  company_id?: string;
  site_id?: string;
  status?: string;
  risk_level?: string | number;
  project_id?: string;
  contractor_id?: string;
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


const PERMISSION_ALIASES: Record<string, Permission> = {
  "documents.read": PERMISSIONS.DOCUMENT_VIEW,
  "documents.write": PERMISSIONS.DOCUMENT_CREATE,
  "documents.sign": PERMISSIONS.DOCUMENT_SIGN,
  "documents.export": PERMISSIONS.DOCUMENT_EXPORT,
  "templates.read": PERMISSIONS.TEMPLATE_VIEW,
  "templates.write": PERMISSIONS.TEMPLATE_EDIT,
  "templates.delete": PERMISSIONS.TEMPLATE_DELETE,
  "files.read": PERMISSIONS.FILE_VIEW,
  "tasks.read": PERMISSIONS.TASK_VIEW,
  "tasks.update": PERMISSIONS.TASK_UPDATE,
  "tasks.write": PERMISSIONS.TASK_UPDATE,
  "risk.read": PERMISSIONS.RISK_VIEW,
  "risk.write": PERMISSIONS.RISK_EDIT,
  "ppe.read": PERMISSIONS.PPE_VIEW,
  "ppe.write": PERMISSIONS.PPE_ISSUE,
  "warehouse.read": PERMISSIONS.WAREHOUSE_VIEW,
  "crm_finance.read": PERMISSIONS.CRM_FINANCE_VIEW,
  "integrations.read": PERMISSIONS.INTEGRATIONS_VIEW,
  "client_portal.read": PERMISSIONS.CLIENT_PORTAL_VIEW,
  "training.read": PERMISSIONS.TRAINING_VIEW,
  "training.write": PERMISSIONS.TRAINING_ASSIGN,
  "incidents.read": PERMISSIONS.INCIDENT_VIEW,
  "incidents.create": PERMISSIONS.INCIDENT_CREATE,
  "incidents.write": PERMISSIONS.INCIDENT_CREATE,
  "inspections.read": PERMISSIONS.INSPECTION_VIEW,
  "inspections.create": PERMISSIONS.INSPECTION_CREATE,
  "inspections.write": PERMISSIONS.INSPECTION_CREATE,
  "audit.read": PERMISSIONS.AUDIT_VIEW,
  "admin.roles": PERMISSIONS.ADMIN_MANAGE_ROLES,
  "admin.tenants": PERMISSIONS.ADMIN_MANAGE_TENANTS,
  "billing.read": PERMISSIONS.REPORTS_VIEW
};

const ROLE_ALIASES: Record<string, Role> = {
  tenant_owner: "owner",
  methodology: "methodist",
  metodist: "methodist",
  projectlead: "project_manager",
  projectlead_manager: "project_manager",
  deloproizvoditel: "office_manager",
  slushatel: "student",
  auditor: "auditor_ro",
  inspector_contractor: "contractor_inspector"
};

const normalizeRole = (role: string): Role | null => {
  const normalized = role.trim().toLowerCase().replace(/[\s/]+/g, "_");
  const alias = ROLE_ALIASES[normalized];
  const resolved = alias ?? normalized;
  return resolved in ROLE_PERMISSIONS ? (resolved as Role) : null;
};

const resolvePermissions = (user: UserDto | null): Set<Permission> => {
  if (!user) return new Set();
  if (user.permissions?.length) {
    const normalized = user.permissions
      .map((permission) => PERMISSION_ALIASES[permission] ?? permission)
      .filter((permission): permission is Permission => ALL_PERMISSIONS.includes(permission as Permission));
    return new Set(normalized);
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
  if (resource?.project_id && user.attributes?.project_ids?.length && !user.attributes.project_ids.includes(resource.project_id)) return false;
  if (resource?.contractor_id && user.attributes?.contractor_ids?.length && !user.attributes.contractor_ids.includes(resource.contractor_id)) return false;
  return true;
};

const ABAC_RULES: Partial<Record<Permission, (user: UserDto, resource?: AbilityResource) => boolean>> = {
  [PERMISSIONS.DOCUMENT_SIGN]: (_user, resource) => ["ready"].includes(resource?.status ?? ""),
  [PERMISSIONS.DOCUMENT_EXPORT]: (_user, resource) => ["ready"].includes(resource?.status ?? ""),
  [PERMISSIONS.RISK_EXPORT]: (_user, resource) => ["approved"].includes(resource?.status ?? ""),
  [PERMISSIONS.RISK_EDIT]: (user, resource) => {
    if (resource?.risk_level == null) return true;
    const raw = resource.risk_level;
    const level = typeof raw === "number" ? raw : ({ low: 1, medium: 2, high: 3, critical: 4 }[String(raw).toLowerCase()] ?? 0);
    const max = user.attributes?.risk_level_max;
    if (typeof max === "number") return level <= max;
    return level < 3;
  },
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
