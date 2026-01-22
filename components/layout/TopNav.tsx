import { LogOut, Moon, Settings, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth";
import { useTheme } from "@/hooks/useTheme";

const navItems = [
  { to: "/companies", translationKey: "navigation.companies" },
  { to: "/persons", translationKey: "navigation.persons" },
  { to: "/templates", translationKey: "navigation.templates" },
  { to: "/packs", translationKey: "navigation.packs" },
  { to: "/documents", translationKey: "navigation.documents" },
  { to: "/files", translationKey: "navigation.files" },
  { to: "/tasks", translationKey: "navigation.tasks" },
  { to: "/risk", translationKey: "navigation.risk" },
  { to: "/npa", translationKey: "navigation.npa" },
  { to: "/audit", translationKey: "navigation.audit" },
  { to: "/settings", translationKey: "navigation.settings" }
];

export const TopNav = () => {
  const { t } = useTranslation();
  const { user, logout } = useAuthStore();
  const [theme, , toggleTheme] = useTheme();

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <span className="text-lg font-semibold">OT/PB Docs</span>
          <nav className="hidden items-center gap-3 text-sm font-medium md:flex">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 transition-colors ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
                }
              >
                {t(item.translationKey)}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={toggleTheme}>
            {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="gap-2">
                <Settings className="h-4 w-4" />
                <span className="hidden sm:inline">{user?.full_name ?? user?.email ?? "Профиль"}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{user?.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => logout()} className="text-destructive">
                <LogOut className="mr-2 h-4 w-4" /> Выйти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
};
