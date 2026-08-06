import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { CATEGORY_ORDER } from "../../../utils/categoryIcons";

interface AccordionState {
  expandedCategories: string[];
  hasInitialized: boolean;
  toggleCategory: (categoryId: string) => void;
  openCategory: (categoryId: string) => void;
  expandAll: () => void;
  collapseAll: () => void;
  initializeDefaults: (categoryIds: string[]) => void;
}

export const useAccordionState = create<AccordionState>()(
  persist(
    (set) => ({
      expandedCategories: [],
      hasInitialized: false,
      toggleCategory: (categoryId: string) =>
        set((state) => {
          const isExpanded = state.expandedCategories.includes(categoryId);
          return {
            expandedCategories: isExpanded
              ? state.expandedCategories.filter((id) => id !== categoryId)
              : [...state.expandedCategories, categoryId],
          };
        }),
      openCategory: (categoryId: string) =>
        set((state) =>
          state.expandedCategories.includes(categoryId)
            ? state
            : { expandedCategories: [...state.expandedCategories, categoryId] },
        ),
      expandAll: () => set({ expandedCategories: [...CATEGORY_ORDER] }),
      collapseAll: () => set({ expandedCategories: [] }),
      initializeDefaults: (categoryIds: string[]) =>
        set((state) =>
          state.hasInitialized
            ? state
            : { expandedCategories: categoryIds, hasInitialized: true },
        ),
    }),
    {
      name: "accordion-state",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
