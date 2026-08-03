import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";

import { Sidebar } from "./Sidebar";
import { SkipLink } from "./SkipLink";

interface AppLayoutProps {
  children?: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="flex min-h-screen bg-background text-gray-900">
      <SkipLink />
      <Sidebar />
      <main id="main-content" className="flex-1 p-6" tabIndex={-1}>
        {children ?? <Outlet />}
      </main>
    </div>
  );
}
