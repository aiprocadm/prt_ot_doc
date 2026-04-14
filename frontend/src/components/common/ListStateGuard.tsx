import type { ReactNode } from "react";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import type { ApiError } from "@/types/dto/common";

type ListStateGuardProps = {
  error?: ApiError | null;
  loading: boolean;
  itemsCount: number;
  loadingLabel: string;
  emptyTitle: string;
  emptyDescription: string;
  onRetry?: () => void;
  children: ReactNode;
};

export const ListStateGuard = ({
  error,
  loading,
  itemsCount,
  loadingLabel,
  emptyTitle,
  emptyDescription,
  onRetry,
  children
}: ListStateGuardProps) => (
  <>
    <ErrorState error={error ?? undefined} onRetry={onRetry} />
    {loading && itemsCount === 0 ? <LoadingScreen label={loadingLabel} /> : null}
    {!loading && !error && itemsCount === 0 ? (
      <EmptyState title={emptyTitle} description={emptyDescription} />
    ) : null}
    {!loading || itemsCount > 0 ? children : null}
  </>
);
