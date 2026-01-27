import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { Outlet } from "react-router-dom";

import { Toaster } from "sonner";

import { RightDrawer } from "@/components/layout/RightDrawer";
import { SideNav } from "@/components/layout/SideNav";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopNav } from "@/components/layout/TopNav";
import { TenantGate } from "@/components/tenant/TenantGate";

interface SidebarContextValue {
  setSidebar: (content: ReactNode) => void;
}

const SidebarContext = createContext<SidebarContextValue | undefined>(undefined);

export const useSidebar = () => {
  const context = useContext(SidebarContext);
  if (!context) throw new Error("useSidebar must be used within MainLayout");
  return context;
};

export const MainLayout = () => {
  const [sidebarContent, setSidebarContent] = useState<ReactNode>(null);
  const contextValue = useMemo(() => ({ setSidebar: setSidebarContent }), []);

  return (
    <SidebarContext.Provider value={contextValue}>
      <TenantGate>
        <div className="min-h-screen bg-background text-foreground">
          <TopNav />
          <div className="flex">
            <SideNav />
            <div className="flex-1">
              <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-4 py-6 lg:flex-row">
                <Sidebar title="Фильтры">{sidebarContent}</Sidebar>
                <main className="flex-1 pb-16">
                  <Outlet />
                </main>
                <RightDrawer />
              </div>
            </div>
          </div>
          <Toaster richColors position="top-right" closeButton />
        </div>
      </TenantGate>
    </SidebarContext.Provider>
  );
};
