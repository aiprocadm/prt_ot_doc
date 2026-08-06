import { useState } from "react";
import { Building2, Menu } from "lucide-react";
import { NavLink } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useNavMenuData } from "@/hooks/useNavMenuData";

const FREQUENT_PATHS = [
  "/dashboard",
  "/documents",
  "/tasks",
  "/packs",
  "/persons",
];

export const MobileNavDrawer = () => {
  const [open, setOpen] = useState(false);
  const { visibleGroups, clientPortalOnlyMode } = useNavMenuData();
  const frequentItems = visibleGroups
    .flatMap((group) => group.items)
    .filter((item) => FREQUENT_PATHS.includes(item.to));
  const otherGroups = visibleGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !FREQUENT_PATHS.includes(item.to)),
    }))
    .filter((group) => group.items.length > 0);

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="h-11 w-11 shrink-0 lg:hidden"
        aria-label="Открыть меню разделов"
        onClick={() => setOpen(true)}
      >
        <Menu className="h-5 w-5" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="fixed left-0 top-0 flex h-[100dvh] max-h-[100dvh] w-[min(100vw,20rem)] max-w-[min(100vw,20rem)] translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none border-r p-0 sm:max-w-xs"
          aria-describedby={undefined}
        >
          <DialogHeader className="border-b px-4 py-4 text-left">
            <DialogTitle className="flex items-center gap-2 text-base font-semibold">
              <Building2 className="h-5 w-5 text-primary" />
              {clientPortalOnlyMode ? "Кабинет клиента" : "OT/ПБ Контур"}
            </DialogTitle>
          </DialogHeader>
          <nav className="flex-1 overflow-y-auto px-3 py-4 text-sm">
            <div className="space-y-6">
              {frequentItems.length ? (
                <div className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Часто
                  </div>
                  <div className="space-y-1">
                    {frequentItems.map((item) => (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        onClick={() => setOpen(false)}
                        className={({ isActive }) =>
                          `flex min-h-11 items-center gap-3 rounded-md px-3 py-2 transition-colors ${
                            isActive
                              ? "bg-primary text-primary-foreground"
                              : "text-muted-foreground hover:text-foreground"
                          }`
                        }
                      >
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </NavLink>
                    ))}
                  </div>
                </div>
              ) : null}
              {otherGroups.map((group) => (
                <div key={group.title} className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Остальное · {group.title}
                  </div>
                  <div className="space-y-1">
                    {group.items.map((item) => (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        onClick={() => setOpen(false)}
                        className={({ isActive }) =>
                          `flex min-h-11 items-center gap-3 rounded-md px-3 py-2 transition-colors ${
                            isActive
                              ? "bg-primary text-primary-foreground"
                              : "text-muted-foreground hover:text-foreground"
                          }`
                        }
                      >
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </NavLink>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </nav>
        </DialogContent>
      </Dialog>
    </>
  );
};
