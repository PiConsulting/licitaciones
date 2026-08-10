import { create } from "zustand";

export type AppTheme = "cedia" | "pi";

interface UIStore {
  sidebarCollapsed: boolean;
  theme: AppTheme;
  toggleSidebar: () => void;
  toggleTheme: () => void;
}

const savedTheme = (localStorage.getItem("app_theme") as AppTheme | null) ?? "cedia";

export const useUIStore = create<UIStore>((set) => ({
  sidebarCollapsed: false,
  theme: savedTheme,
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  toggleTheme: () =>
    set((state) => {
      const next: AppTheme = state.theme === "cedia" ? "pi" : "cedia";
      localStorage.setItem("app_theme", next);
      return { theme: next };
    }),
}));
