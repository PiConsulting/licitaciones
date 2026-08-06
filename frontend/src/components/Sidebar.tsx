import {
  ChevronLeft,
  FileText,
  LayoutDashboard,
  LogOut,
  User,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { useUIStore } from "../store/useUIStore";
import { cn } from "../utils/cn";

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();

  const navItems = [
    { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/analyze", icon: FileText, label: "Analizar nuevo pliego" },
  ];

  return (
    <aside
      className={cn(
        "sticky top-0 h-screen self-start overflow-y-auto border-r border-gray-200 bg-surface transition-all duration-200 ease-in-out",
        sidebarCollapsed ? "w-16" : "w-52",
      )}
      aria-label="Barra lateral"
    >
      <div className="flex h-full flex-col">
        <div className="border-b border-gray-200 px-4 py-4">
          <div className="flex items-start justify-between gap-2">
            <div className={cn("min-w-0", sidebarCollapsed && "sr-only")}>
              <p className="text-sm font-semibold text-cedia-primary">CedIA</p>
              <p className="mt-0.5 text-xs text-gray-500">Análisis de pliegos</p>
            </div>
          <button
            type="button"
            aria-label={sidebarCollapsed ? "Expandir menú" : "Colapsar menú"}
            onClick={toggleSidebar}
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md text-gray-700 hover:bg-gray-50"
          >
            <ChevronLeft className={cn("transition-transform duration-200", sidebarCollapsed && "rotate-180")} />
          </button>
          </div>
        </div>

        <nav className="flex-1" role="navigation" aria-label="Navegación principal">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex min-h-[44px] items-center gap-3 px-4 py-3 text-xs font-medium text-gray-700 hover:bg-gray-50",
                  isActive && "border-l-4 border-primary bg-primary-light text-primary",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={20} aria-hidden="true" />
                  <span
                    className={cn(sidebarCollapsed && "sr-only")}
                    aria-current={isActive ? "page" : undefined}
                  >
                    {label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-gray-200 px-4 py-4">
          <div className="mb-2 flex items-center gap-3 text-xs text-gray-700">
            <User size={18} />
            <span className={cn(sidebarCollapsed && "sr-only")}>Usuario Test</span>
          </div>
          <button
            type="button"
            className="inline-flex min-h-[44px] min-w-[44px] items-center gap-2 rounded-md text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            <LogOut size={16} />
            <span className={cn(sidebarCollapsed && "sr-only")}>Cerrar Sesión</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
