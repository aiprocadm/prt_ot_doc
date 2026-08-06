import type { ReactNode } from "react";

interface FilterFieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  children: ReactNode;
}

export const FilterField = ({
  label,
  htmlFor,
  hint,
  children,
}: FilterFieldProps) => (
  <div className="flex flex-col gap-1">
    <label
      htmlFor={htmlFor}
      className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
    >
      {label}
    </label>
    {children}
    {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
  </div>
);
