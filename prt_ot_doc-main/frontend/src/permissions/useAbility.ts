import { useMemo } from "react";

import { buildAbility } from "@/permissions/ability";
import { useAuthStore } from "@/stores/auth";

export const useAbility = () => {
  const user = useAuthStore((state) => state.user);
  return useMemo(() => buildAbility(user), [user]);
};
