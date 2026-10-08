import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { BUSINESS_UNITS } from "../../config/businessUnits";
import { ChecklistPage } from "./ChecklistPage";

vi.mock("../../api/tracking", () => ({
  listTrackingComments: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../components/ToastContainer", () => ({
  useToast: () => ({ addToast: vi.fn() }),
}));

const idle = { mutateAsync: vi.fn(), isPending: false };
const startTracking = vi.hoisted(() => ({ mutateAsync: vi.fn().mockResolvedValue({}), isPending: false }));

vi.mock("../analysis-detail/hooks/useTrackingMutations", () => ({
  trackingItemCommentsQueryKey: (analysisId: string, categoryKey: string) => [
    "tracking-comments",
    analysisId,
    categoryKey,
    "items",
  ],
  useCompleteTracking: () => idle,
  useCreateTrackingComment: () => idle,
  useDeleteTrackingComment: () => idle,
  useStartTracking: () => startTracking,
  useUpdateTrackingCategoryStatus: () => idle,
  useUpdateTrackingComment: () => idle,
  useUpdateTrackingItemStatus: () => idle,
}));

const KEYS = [
  "objeto_alcance",
  "riesgos",
  "requisitos_admisibilidad",
  "garantias",
  "plazos_clave",
  "criterios_evaluacion",
  "causales_rechazo",
  "anexos_obligatorios",
];

const tracking = {
  id: "t1",
  type: "tracking",
  analysis_id: "an-1",
  version_id: "v1",
  status: "active",
  started_by: "u1",
  started_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
  summary: { total_categories: 8, not_reviewed: 0, in_review: 8, closed: 0, closed_percentage: 0 },
  categories: KEYS.map((key) => ({
    category_key: key,
    status: "in_review",
    comments_count: 0,
    items: [
      {
        tracking_item_id: `${key}-1`,
        category_key: key,
        status: "not_evaluated",
        comments_count: 0,
        source_item_ref: { version_id: "v1", field_name: "campo", document_id: "d1", page: 1 },
      },
    ],
  })),
};

vi.mock("../analysis-detail/hooks/useAnalysisDetail", () => ({
  useAnalysisDetail: () => ({
    isLoading: false,
    isError: false,
    data: {
      id: "an-1",
      analysis_name: "LP 1/2026",
      business_unit: BUSINESS_UNITS[0],
      tracking,
      current_version: { extracted_data: {} },
    },
  }),
}));

describe("ChecklistPage", () => {
  test("no muestra la categoría Objeto y alcance y cuenta solo las categorías del checklist", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/analysis/an-1/checklist"]}>
          <Routes>
            <Route path="/analysis/:analysisId/checklist" element={<ChecklistPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.queryByText("Objeto y alcance")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("checklist-category-card")).toHaveLength(7);
    expect(screen.getByRole("button", { name: /Todas/ })).toHaveTextContent("7");
  });

  test("el evento de reanudar dispara la reanudación del seguimiento del análisis", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/analysis/an-1/checklist"]}>
          <Routes>
            <Route path="/analysis/:analysisId/checklist" element={<ChecklistPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent("checklist:resume-tracking"));
    });

    await waitFor(() => expect(startTracking.mutateAsync).toHaveBeenCalledWith({ analysisId: "an-1" }));
  });
});
