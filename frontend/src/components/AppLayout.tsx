import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { Outlet } from "react-router-dom";

import { AppHeader } from "./AppHeader";
import { Sidebar } from "./Sidebar";
import { SkipLink } from "./SkipLink";

interface AppLayoutProps {
  children?: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const location = useLocation();
  const isAnalyzePage = location.pathname.startsWith("/analyze");
  const isDashboardPage = location.pathname === "/";

  return (
    <div className={["flex min-h-screen text-gray-900", isDashboardPage ? "bg-cedi-surface-tint" : "bg-background"].join(" ")}>
      <SkipLink />
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader />
        <main
          id="main-content"
          className={isAnalyzePage ? "flex-1 px-6 pb-12 pt-8" : "flex-1 p-6"}
          tabIndex={-1}
        >
          {children ?? <Outlet />}
        </main>
      </div>
    </div>
  );
}
