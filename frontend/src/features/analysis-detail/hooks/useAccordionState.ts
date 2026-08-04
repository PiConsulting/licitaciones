import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { CATEGORY_ORDER } from "../../../utils/categoryIcons";

interface AccordionState {
  expandedCategories: string[];
  toggleCategory: (categoryId: string) => void;
  expandAll: () => void;
  collapseAll: () => void;
}

export const useAccordionState = create<AccordionState>()(
  persist(
    (set) => ({
      expandedCategories: [],
      toggleCategory: (categoryId: string) =>
        set((state) => {
          const isExpanded = state.expandedCategories.includes(categoryId);
          return {
            expandedCategories: isExpanded
              ? state.expandedCategories.filter((id) => id !== categoryId)
              : [...state.expandedCategories, categoryId],
          };
        }),
      expandAll: () => set({ expandedCategories: [...CATEGORY_ORDER] }),
      collapseAll: () => set({ expandedCategories: [] }),
    }),
    {
      name: "accordion-state",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
