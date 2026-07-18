import { PERMISSIONS, type Permission } from "@/permissions/permissions";
import { workspaceApi } from "@/api/workspace";

const shouldPrioritizeAttentionHub = (can: (permission: Permission) => boolean) => {
  const hasWorkspacePermission = can(PERMISSIONS.DASHBOARD_VIEW);
  const hasOtAttentionScope =
    can(PERMISSIONS.TRAINING_VIEW) ||
    can(PERMISSIONS.MEDICAL_VIEW) ||
    can(PERMISSIONS.PPE_VIEW) ||
    can(PERMISSIONS.INSPECTION_VIEW);

  return hasWorkspacePermission && hasOtAttentionScope;
};

const LANDING_PRIORITY: Array<{ permission: Permission; route: string }> = [
  { permission: PERMISSIONS.DASHBOARD_VIEW, route: "/dashboard" },
  { permission: PERMISSIONS.COMPANY_VIEW, route: "/companies" },
  { permission: PERMISSIONS.PERSON_VIEW, route: "/persons" },
  { permission: PERMISSIONS.DOCUMENT_VIEW, route: "/documents" },
  { permission: PERMISSIONS.FILE_VIEW, route: "/archive" },
  { permission: PERMISSIONS.PACK_VIEW, route: "/packs" },
  { permission: PERMISSIONS.TASK_VIEW, route: "/tasks" },
  { permission: PERMISSIONS.CLIENT_PORTAL_VIEW, route: "/client-portal/dashboard" }
];

/**
 * Get role-based landing route using workspace configuration.
 * Falls back to permission-based routing if workspace config fetch fails.
 */
export const getLandingRoute = async (can: (permission: Permission) => boolean): Promise<string> => {
  try {
    // Try to fetch role-based workspace config (Phase 1.1)
    const workspaceConfig = await workspaceApi.getUserWorkspaceConfig();
    if (workspaceConfig?.dashboard_route) {
      return workspaceConfig.dashboard_route;
    }
  } catch {
    // Fallback to permission-based routing if workspace config unavailable
  }

  if (shouldPrioritizeAttentionHub(can)) {
    return "/workspace/attention";
  }

  const match = LANDING_PRIORITY.find((candidate) => can(candidate.permission));
  return match?.route ?? "/no-access";
};
