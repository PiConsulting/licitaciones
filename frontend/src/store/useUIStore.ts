import { create } from "zustand";

export type AppTheme = "cedia" | "pi";

interface UIStore {
  sidebarCollapsed: boolean;
  theme: AppTheme;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleTheme: () => void;
}

const savedTheme = (localStorage.getItem("app_theme") as AppTheme | null) ?? "cedia";

export const useUIStore = create<UIStore>((set) => ({
  // 2026-09-01: colapsado por default -- se expande manualmente con el
  // botón de flecha y se vuelve a colapsar solo al elegir una sección (ver
  // Sidebar.tsx, setSidebarCollapsed(true) en el onClick de cada NavLink).
  sidebarCollapsed: true,
  theme: savedTheme,
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  toggleTheme: () =>
    set((state) => {
      const next: AppTheme = state.theme === "cedia" ? "pi" : "cedia";
      localStorage.setItem("app_theme", next);
      return { theme: next };
    }),
}));
