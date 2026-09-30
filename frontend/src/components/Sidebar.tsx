import type { ReactNode } from "react";
import { ChevronLeft } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";

import { logout } from "../api/auth";
import { useSession } from "../auth/session";
import { getUserRoleLabel } from "../config/userRoles";
import { useUIStore } from "../store/useUIStore";
import { cn } from "../utils/cn";

interface SidebarIconProps {
  children: ReactNode;
}

function SidebarIcon({ children }: SidebarIconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" x2="9" y1="12" y2="12" />
    </svg>
  );
}

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  disabled?: boolean;
}

export function Sidebar() {
  const navigate = useNavigate();
  const sidebarCollapsed = useUIStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);

  const session = useSession();
  const userName = session.name;
  const userEmail = session.email;
  const displayUser = userName || userEmail || "Usuario";

  const displayRole =
    [getUserRoleLabel(session.role), session.isSuperadmin ? "" : session.businessUnit]
      .filter(Boolean)
      .join(" · ") || "CedIA";
  const initialsSource = userName || userEmail || "US";
  const initials = initialsSource
    .replace(/[^a-zA-Z\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "US";

  const navItems: NavItem[] = [
    {
      to: "/",
      label: "Home",
      icon: (
        <SidebarIcon>
          <path d="M3 3h7v9H3z M14 3h7v5h-7z M14 12h7v9h-7z M3 16h7v5H3z" />
        </SidebarIcon>
      ),
    },
    {
      to: "#",
      label: "Buscar pliegos",
      disabled: true,
      icon: (
        <SidebarIcon>
          <path d="M11 3a8 8 0 1 0 0 16a8 8 0 1 0 0-16 M21 21l-4.3-4.3" />
        </SidebarIcon>
      ),
    },
    {
      to: "/analyze",
      label: "Analizar nuevo pliego",
      icon: (
        <SidebarIcon>
          <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z M14 2v4a2 2 0 0 0 2 2h4 M12 18v-6 M9 15h6" />
        </SidebarIcon>
      ),
    },
  ];

  const adminItems: NavItem[] = session.isSuperadmin
    ? [
        {
          to: "/usuarios",
          label: "Usuarios del sistema",
          icon: (
            <SidebarIcon>
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8a4 4 0 1 0 0-8 M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75" />
            </SidebarIcon>
          ),
        },
      ]
    : [];

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const renderNavItem = ({ to, icon, label, disabled }: NavItem) => (
    disabled ? (
      <button
        key={label}
        type="button"
        aria-disabled="true"
        title="Próximamente"
        className={cn(
          "group flex min-h-[44px] w-full items-center rounded-[10px] bg-transparent text-left text-[13px] font-semibold text-white/75",
          sidebarCollapsed ? "justify-center px-0" : "gap-3 pl-4 pr-3",
        )}
      >
        {icon}
        <span className={cn("truncate", sidebarCollapsed && "sr-only")}>{label}</span>
        <span className="sr-only">Próximamente</span>
      </button>
    ) : (
      <NavLink
        key={to}
        to={to}
        className={({ isActive }) =>
          cn(
            "flex min-h-[44px] items-center rounded-[10px] text-[13px] font-semibold no-underline transition-colors",
            sidebarCollapsed ? "justify-center px-0" : "gap-3 pl-4 pr-3",
            isActive
              ? "bg-white/[.12] text-white [box-shadow:inset_3px_0_0_#7FF3DE]"
              : "bg-transparent text-white/75 hover:bg-white/10 hover:text-white",
          )
        }
      >
        {({ isActive }) => (
          <>
            {icon}
            <span className={cn("truncate", sidebarCollapsed && "sr-only")} aria-current={isActive ? "page" : undefined}>
              {label}
            </span>
          </>
        )}
      </NavLink>
    )
  );

  return (
    <aside
      className={cn(
        "sticky top-0 h-screen self-start overflow-y-auto bg-[#003C6B] text-white transition-[width] duration-200",
        sidebarCollapsed ? "w-[72px]" : "w-[232px]",
      )}
      aria-label="Barra lateral"
    >
      <div className="flex h-full flex-col">
        <div className={cn("relative border-b border-white/[.12] pb-4 pt-5", sidebarCollapsed ? "px-3" : "pl-6 pr-5")}>
          <div className={cn("flex items-center", sidebarCollapsed ? "flex-col justify-center gap-2" : "justify-between")}>
            <div className="flex items-center gap-3">
            <img
              src="/cedi-isotipo.png"
              alt="CEDI"
              className="h-8 w-8 object-contain [filter:brightness(0)_invert(1)]"
            />
              <div className={cn("min-w-0", sidebarCollapsed && "sr-only")}>
                <p className="font-display text-[16px] font-bold leading-[1.1]">CedIA</p>
                <p className="mt-0.5 text-[11px] text-white/70">Análisis de pliegos</p>
              </div>
            </div>
            <button
              type="button"
              onClick={toggleSidebar}
              aria-label={sidebarCollapsed ? "Expandir barra lateral" : "Colapsar barra lateral"}
              title={sidebarCollapsed ? "Expandir barra lateral" : "Colapsar barra lateral"}
              className={cn(
                "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-white/75 transition-colors hover:bg-white/10 hover:text-white",
                sidebarCollapsed && "mt-1",
              )}
            >
              <ChevronLeft size={18} className={cn("transition-transform", sidebarCollapsed && "rotate-180")} />
            </button>
          </div>
        </div>

        <nav className={cn("flex flex-1 flex-col gap-1", sidebarCollapsed ? "p-2" : "p-3")} role="navigation" aria-label="Navegación principal">
          {navItems.map(renderNavItem)}
          {adminItems.length > 0 ? (
            <>
              <div
                className={cn(
                  "mb-1 mt-3 border-t border-white/[.12] pt-3 text-[10px] font-bold uppercase tracking-[.14em] text-white/55",
                  sidebarCollapsed ? "mx-1" : "mx-3",
                )}
              >
                <span className={cn(sidebarCollapsed && "sr-only")}>Superadmin</span>
              </div>
              {adminItems.map(renderNavItem)}
            </>
          ) : null}
        </nav>

        <div className={cn("flex items-center border-t border-white/[.12]", sidebarCollapsed ? "justify-center p-3" : "gap-3 p-4")}>
          <div className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[linear-gradient(145deg,#0099DB,#2F4EF8)] font-display text-xs font-bold text-cedi-white">
            {initials}
          </div>
          <div className={cn("min-w-0 flex-1", sidebarCollapsed && "sr-only")}>
            <p className="truncate text-[13px] font-semibold leading-[1.15] text-white">{displayUser}</p>
            <p className="truncate text-[11px] leading-[1.15] text-white/70">{displayRole}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            aria-label="Cerrar sesión"
            title="Cerrar sesión"
            className={cn(
              "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border-0 bg-transparent text-white/75 transition-colors hover:bg-white/10 hover:text-white",
              sidebarCollapsed && "sr-only",
            )}
          >
            <LogoutIcon />
          </button>
        </div>
      </div>
    </aside>
  );
}
