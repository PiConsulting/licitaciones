import {
  ChevronLeft,
  FileText,
  LayoutDashboard,
  LogOut,
  User,
} from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { logout } from "../api/auth";
import { useUIStore } from "../store/useUIStore";
import { cn } from "../utils/cn";

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, theme, toggleTheme } = useUIStore();
  const navigate = useNavigate();

  const isPi = theme === "pi";

  const userName = localStorage.getItem("user_name")?.trim();
  const userEmail = localStorage.getItem("user_email")?.trim();
  const displayUser = userName || userEmail || "Usuario";

  const navItems = [
    { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/analyze", icon: FileText, label: "Analizar nuevo pliego" },
  ];

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <aside
      className={cn(
        "sticky top-0 h-screen self-start overflow-y-auto transition-all duration-200 ease-in-out",
        isPi
          ? "border-r border-[#FFF100]/20 bg-pi-black"
          : "border-r border-gray-200 bg-surface",
        sidebarCollapsed ? "w-16" : "w-52",
      )}
      aria-label="Barra lateral"
    >
      <div className="flex h-full flex-col">
        {/* Header */}
        <div
          className={cn(
            "border-b px-4 py-4",
            isPi ? "border-[#FFF100]/20" : "border-gray-200",
          )}
        >
          <div
            className={cn(
              "flex gap-2",
              sidebarCollapsed ? "flex-col items-center" : "flex-row items-start justify-between",
            )}
          >
            {isPi ? (
              <img
                src={sidebarCollapsed ? "/pi-logo-2.png" : "/pi-logo.png"}
                alt="Pi Consulting"
                className={sidebarCollapsed ? "h-7 w-7 object-contain" : "h-8 w-auto"}
              />
            ) : (
              <div className={cn("min-w-0", sidebarCollapsed && "sr-only")}>
                <p className="text-sm font-semibold text-cedia-primary">CedIA</p>
                <p className="mt-0.5 text-xs text-gray-500">Análisis de pliegos</p>
              </div>
            )}
            {!isPi && sidebarCollapsed && <span className="sr-only">CedIA</span>}
            <button
              type="button"
              aria-label={sidebarCollapsed ? "Expandir menú" : "Colapsar menú"}
              onClick={toggleSidebar}
              className={cn(
                "inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md",
                isPi
                  ? "text-pi-yellow hover:bg-[#FFF100]/10"
                  : "text-gray-700 hover:bg-gray-50",
              )}
            >
              <ChevronLeft
                className={cn("transition-transform duration-200", sidebarCollapsed && "rotate-180")}
              />
            </button>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1" role="navigation" aria-label="Navegación principal">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex min-h-[44px] items-center gap-3 px-4 py-3 text-xs font-medium transition-colors",
                  isPi
                    ? cn(
                        "text-white/80 hover:bg-[#FFF100]/10",
                        isActive && "border-l-4 border-pi-yellow bg-[#FFF100]/10",
                      )
                    : cn(
                        "text-gray-700 hover:bg-gray-50",
                        isActive && "border-l-4 border-primary bg-primary-light",
                      ),
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

        {/* Footer */}
        <div
          className={cn(
            "border-t px-4 py-4",
            isPi ? "border-[#FFF100]/20" : "border-gray-200",
          )}
        >
          {/* User row + theme toggle */}
          <div className="mb-2 flex items-center justify-between gap-2">
            <div
              className={cn(
                "flex min-w-0 items-center gap-2 text-xs",
                isPi ? "text-white/80" : "text-gray-700",
              )}
            >
              <User size={18} className={cn(isPi && "text-pi-yellow")} />
              <span className={cn("truncate", sidebarCollapsed && "sr-only")}>{displayUser}</span>
            </div>
            {!sidebarCollapsed && (
              <button
                type="button"
                onClick={toggleTheme}
                aria-label={`Cambiar al tema ${isPi ? "CEDI" : "PI"}`}
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold leading-none transition-colors",
                  isPi
                    ? "bg-pi-yellow text-pi-black hover:bg-[#FFF100]/80"
                    : "bg-gray-200 text-gray-700 hover:bg-gray-300",
                )}
              >
                {isPi ? "CEDI" : "PI"}
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className={cn(
              "inline-flex min-h-[44px] min-w-[44px] items-center gap-2 rounded-md text-xs font-medium",
              isPi
                ? "text-white/70 hover:bg-[#FFF100]/10 hover:text-white"
                : "text-gray-700 hover:bg-gray-50",
            )}
          >
            <LogOut size={16} />
            <span className={cn(sidebarCollapsed && "sr-only")}>Cerrar Sesión</span>
          </button>

          {/* COE IA attribution */}
          {!sidebarCollapsed && (
            <p
              className={cn(
                "mt-3 text-[10px] font-semibold tracking-widest",
                isPi ? "text-pi-yellow/50" : "text-gray-400",
              )}
            >
              COE IA
            </p>
          )}
        </div>
      </div>
    </aside>
  );
}
