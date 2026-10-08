import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ChecklistCategoryCard } from "./ChecklistCategoryCard";
import type { CategoryData } from "../analysis-detail/types";
import type { TrackingCategory } from "../../types/tracking";

const listTrackingComments = vi.fn();

vi.mock("../../api/tracking", () => ({
  listTrackingComments: (...args: unknown[]) => listTrackingComments(...args),
}));

const category: CategoryData = {
  items: [],
  confidence: 0,
  source_references: [],
  extraction_status: "success",
  summary: "",
  is_reviewed: false,
  narrative: {
    blocks: [
      {
        type: "bullet_list",
        items: [
          { titulo: "Inscripción vigente", text: "Presentar constancia.", confidence_level: "high", source_ids: [0] },
          { titulo: "Garantía de oferta", text: "Acompañar la garantía.", confidence_level: "high", source_ids: [1] },
        ],
      },
    ],
    sources: [
      { id: 0, document_id: "doc-1", document_name: "Pliego", page: 3, text: "a" },
      { id: 1, document_id: "doc-1", document_name: "Pliego", page: 4, text: "b" },
    ],
  },
};

function buildTrackingCategory(status: TrackingCategory["status"] = "in_review"): TrackingCategory {
  return {
    category_key: "requisitos_admisibilidad",
    status,
    comments_count: 0,
    items: [
      {
        tracking_item_id: "item-1",
        category_key: "requisitos_admisibilidad",
        status: "not_evaluated",
        comments_count: 2,
        source_item_ref: { version_id: "v1", field_name: "a", document_id: "doc-1", page: 3 },
      },
      {
        tracking_item_id: "item-2",
        category_key: "requisitos_admisibilidad",
        status: "not_evaluated",
        comments_count: 0,
        source_item_ref: { version_id: "v1", field_name: "b", document_id: "doc-1", page: 4 },
      },
    ],
  };
}

function renderCard(overrides: Partial<Parameters<typeof ChecklistCategoryCard>[0]> = {}) {
  const props = {
    analysisId: "an-1",
    categoryId: "requisitos_admisibilidad" as const,
    category,
    trackingCategory: buildTrackingCategory(),
    isOpen: true,
    readOnly: false,
    actionLoading: false,
    onToggleOpen: vi.fn(),
    onToggleClosed: vi.fn(),
    onChangeItemStatus: vi.fn(),
    onCreateComment: vi.fn().mockResolvedValue(undefined),
    onUpdateComment: vi.fn().mockResolvedValue(undefined),
    onDeleteComment: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ChecklistCategoryCard {...props} />
    </QueryClientProvider>,
  );
  return { ...props, unmount: view.unmount };
}

const itemComment = {
  id: "c1",
  analysis_id: "an-1",
  version_id: "v1",
  category_key: "requisitos_admisibilidad",
  scope: "checklist_item",
  tracking_item_id: "item-1",
  content: "Falta la constancia",
  created_by: "u1",
  created_by_name: "Ana",
  created_at: "2026-09-29T10:00:00Z",
};

describe("ChecklistCategoryCard comentarios por ítem", () => {
  beforeEach(() => {
    listTrackingComments.mockReset();
    listTrackingComments.mockResolvedValue([]);
  });

  test("cada ítem tiene su botón Comentar y no hay panel de comentarios de categoría", () => {
    renderCard();

    expect(screen.getByRole("button", { name: "Comentar: Inscripción vigente" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comentar: Garantía de oferta" })).toBeInTheDocument();
    expect(screen.queryByText("Agregar comentario")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Comentarios de seguimiento/ })).not.toBeInTheDocument();
  });

  test("muestra el comentario como Autor · texto solo en el ítem al que pertenece", async () => {
    listTrackingComments.mockResolvedValue([itemComment]);
    renderCard();

    const text = await screen.findByText(/Falta la constancia/);
    expect(text).toHaveTextContent("Ana · Falta la constancia");
    expect(listTrackingComments).toHaveBeenCalledWith("an-1", "requisitos_admisibilidad", {
      scope: "checklist_item",
    });
    expect(screen.getAllByText(/Falta la constancia/)).toHaveLength(1);
  });

  test("guardar un comentario lo envía con el id del ítem y cierra el editor", async () => {
    const props = renderCard();

    fireEvent.click(screen.getByRole("button", { name: "Comentar: Garantía de oferta" }));
    fireEvent.change(await screen.findByLabelText("Nuevo comentario: Garantía de oferta"), {
      target: { value: "Vence en octubre" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar comentario" }));

    await waitFor(() => expect(props.onCreateComment).toHaveBeenCalledWith("item-2", "Vence en octubre"));
    await waitFor(() =>
      expect(screen.queryByLabelText("Nuevo comentario: Garantía de oferta")).not.toBeInTheDocument(),
    );
  });

  test("con la categoría cerrada no se puede comentar ni editar", async () => {
    listTrackingComments.mockResolvedValue([itemComment]);
    renderCard({ trackingCategory: buildTrackingCategory("closed") });

    expect(await screen.findByText(/Falta la constancia/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comentar: Garantía de oferta" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
  });

  test("el encabezado muestra el total de comentarios de la categoría solo si hay al menos uno", () => {
    renderCard();

    expect(screen.getByTestId("category-comments-badge")).toHaveTextContent("2 comentarios");
  });

  test("usa singular con un comentario y no muestra el badge sin comentarios", () => {
    const withOne = buildTrackingCategory();
    withOne.items[0].comments_count = 1;
    withOne.items[1].comments_count = 0;
    const { unmount } = renderCard({ trackingCategory: withOne });
    expect(screen.getByTestId("category-comments-badge")).toHaveTextContent("1 comentario");
    expect(screen.getByTestId("category-comments-badge")).not.toHaveTextContent("comentarios");
    unmount();

    const none = buildTrackingCategory();
    none.items.forEach((item) => {
      item.comments_count = 0;
    });
    renderCard({ trackingCategory: none });
    expect(screen.queryByTestId("category-comments-badge")).not.toBeInTheDocument();
  });
});
