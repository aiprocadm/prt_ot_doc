import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import { cn } from "@/utils/cn";

interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export const Breadcrumb = ({ items }: BreadcrumbProps) => {
  return (
    <nav
      aria-label="Навигационная цепочка"
      className="flex items-center space-x-1 text-sm text-muted-foreground"
    >
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        const content =
          item.to && !isLast ? (
            <Link className="hover:text-foreground" to={item.to}>
              {item.label}
            </Link>
          ) : (
            <span className={cn(isLast && "text-foreground font-medium")}>
              {item.label}
            </span>
          );
        return (
          <span key={item.label} className="flex items-center space-x-1">
            {index > 0 && (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            )}
            {content}
          </span>
        );
      })}
    </nav>
  );
};
