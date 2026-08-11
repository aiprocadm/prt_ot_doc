import type { ReactNode } from "react";

import { Can } from "@/components/permissions/Can";
import type { AbilityResource } from "@/permissions/ability";
import type { Permission } from "@/permissions/permissions";

interface PermissionGateProps {
  permission: Permission;
  resource?: AbilityResource;
  fallback?: ReactNode;
  children: ReactNode;
}

export const PermissionGate = ({
  permission,
  resource,
  fallback = null,
  children,
}: PermissionGateProps) => (
  <Can permission={permission} resource={resource} fallback={fallback}>
    {children}
  </Can>
);
