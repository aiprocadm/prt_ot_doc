import { useAbility } from "@/permissions/useAbility";
import { PERMISSIONS } from "@/permissions/permissions";

const STAFF_PERMISSIONS_FOR_FULL_NAV = [
  PERMISSIONS.DASHBOARD_VIEW,
  PERMISSIONS.COMPANY_VIEW,
  PERMISSIONS.DOCUMENT_VIEW,
  PERMISSIONS.PACK_VIEW,
  PERMISSIONS.TASK_VIEW,
  PERMISSIONS.REPORTS_VIEW,
  PERMISSIONS.ADMIN_MANAGE_ROLES,
] as const;

/** Пользователь видит только кабинет клиента (как в SideNav). */
export const useClientPortalOnlyMode = (): boolean => {
  const { can } = useAbility();
  return (
    can(PERMISSIONS.CLIENT_PORTAL_VIEW) &&
    !STAFF_PERMISSIONS_FOR_FULL_NAV.some((permission) => can(permission))
  );
};
