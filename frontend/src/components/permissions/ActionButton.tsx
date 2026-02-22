import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";
import type { AbilityResource } from "@/permissions/ability";
import type { Permission } from "@/permissions/permissions";
import { useAbility } from "@/permissions/useAbility";

type ButtonProps = ComponentProps<typeof Button>;

interface ActionButtonProps extends ButtonProps {
  permission: Permission;
  abilityResource?: AbilityResource;
  hideWhenDenied?: boolean;
  disabledReason?: string;
}

export const ActionButton = ({
  permission,
  abilityResource,
  hideWhenDenied = false,
  disabledReason = "Недостаточно прав",
  disabled,
  title,
  ...props
}: ActionButtonProps) => {
  const { can } = useAbility();
  const allowed = can(permission, abilityResource);

  if (!allowed && hideWhenDenied) return null;

  return (
    <Button
      {...props}
      disabled={disabled || !allowed}
      title={!allowed ? disabledReason : title}
      aria-disabled={!allowed || disabled}
    />
  );
};
