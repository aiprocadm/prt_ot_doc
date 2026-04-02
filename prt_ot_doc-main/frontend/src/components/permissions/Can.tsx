import type { ReactNode } from "react";

import type { AbilityResource } from "@/permissions/ability";
import type { Permission } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";

interface CanProps {
  permission: Permission;
  resource?: AbilityResource;
  fallback?: ReactNode;
  children: ReactNode | ((allowed: boolean) => ReactNode);
}

export const Can = ({ permission, resource, fallback = null, children }: CanProps) => {
  const { can } = useAbility();
  const allowed = can(permission, resource);

  if (typeof children === "function") {
    return <>{children(allowed)}</>;
  }

  return allowed ? <>{children}</> : <>{fallback}</>;
};
