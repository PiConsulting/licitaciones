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
  // Colapsado por default; se expande con el botón y vuelve a colapsar al elegir sección (ver Sidebar.tsx).
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
