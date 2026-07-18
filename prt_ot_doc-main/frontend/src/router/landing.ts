import { PERMISSIONS, type Permission } from "@/permissions/permissions";

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

export const getLandingRoute = (can: (permission: Permission) => boolean) => {
  const match = LANDING_PRIORITY.find((candidate) => can(candidate.permission));
  return match?.route ?? "/no-access";
};

