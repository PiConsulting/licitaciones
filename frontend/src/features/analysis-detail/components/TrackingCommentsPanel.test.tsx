import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";

import { TrackingCommentsPanel } from "./TrackingCommentsPanel";
import type { TrackingCategory, TrackingComment } from "../../../types/tracking";
import { trackingCommentsQueryKey } from "../hooks/useTrackingMutations";

function createTrackingCategory(items: TrackingCategory["items"] = []): TrackingCategory {
  return {
    category_key: "objeto_alcance",
    status: "in_review",
    items,
    comments_count: 0,
  };
}

function renderPanel(category = createTrackingCategory(), options?: { analysisId?: string; comments?: TrackingComment[] }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const analysisId = options?.analysisId ?? "";
  if (analysisId && options?.comments) {
    queryClient.setQueryData(trackingCommentsQueryKey(analysisId, category.category_key), options.comments);
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <TrackingCommentsPanel
        analysisId={analysisId}
        category={category}
        isClosed={false}
        isReadOnly={false}
        onCreateComment={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

describe("TrackingCommentsPanel", () => {
  test("solo permite comentario de categoría cuando la categoría no tiene ítems", async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(screen.queryByRole("option", { name: "Comentario de categoría" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Agregar comentario" }));

    expect(screen.queryByRole("option", { name: "Comentario de categoría" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Comentario de ítem" })).not.toBeInTheDocument();
  });

  test("solo permite comentario de categoría aunque la categoría tenga ítems", async () => {
    const user = userEvent.setup();
    const category = createTrackingCategory([
      {
        tracking_item_id: "item-1",
        category_key: "objeto_alcance",
        status: "not_evaluated",
        source_item_ref: {
          version_id: "version-1",
          field_name: "Objeto",
        },
      },
    ]);

    renderPanel(category);

    await user.click(screen.getByRole("button", { name: "Agregar comentario" }));

    expect(screen.queryByRole("option", { name: "Comentario de categoría" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Comentario de ítem" })).not.toBeInTheDocument();
  });

  test("muestra comentarios guardados al desplegar el historial", async () => {
    const user = userEvent.setup();
    renderPanel(createTrackingCategory(), {
      analysisId: "analysis-1",
      comments: [
        {
          id: "comment-1",
          analysis_id: "analysis-1",
          version_id: "version-1",
          category_key: "objeto_alcance",
          scope: "category",
          content: "Revisar alcance con legales.",
          created_by: "user-1",
          created_by_name: "Agostina Torres",
          created_at: "2026-08-19T12:30:00Z",
        },
      ],
    });

    expect(screen.queryByText("Historial de comentarios")).not.toBeInTheDocument();
    expect(screen.queryByText("Revisar alcance con legales.")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Ver historial" }));

    expect(screen.getByText("Historial de comentarios")).toBeInTheDocument();
    expect(screen.getByText("Revisar alcance con legales.")).toBeInTheDocument();
    expect(screen.getByText("Creado por Agostina Torres")).toBeInTheDocument();
    expect(screen.getByText("Categoría")).toBeInTheDocument();
  });

  test("cuando el comentario lo edita otra persona, muestra marca de auditoría discreta", async () => {
    const user = userEvent.setup();
    renderPanel(createTrackingCategory(), {
      analysisId: "analysis-1",
      comments: [
        {
          id: "comment-2",
          analysis_id: "analysis-1",
          version_id: "version-1",
          category_key: "objeto_alcance",
          scope: "category",
          content: "Texto ajustado",
          created_by: "user-1",
          created_by_name: "Autora Original",
          created_at: "2026-08-19T12:30:00Z",
          edited_by: "user-2",
          edited_by_name: "Editor Externo",
          edited_at: "2026-08-19T13:30:00Z",
        },
      ],
    });

    await user.click(screen.getByRole("button", { name: "Ver historial" }));

    expect(screen.getByText(/Editado por Editor Externo/i)).toBeInTheDocument();
  });

  test("cuando está en read-only no muestra acciones de editar/eliminar", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    const category = createTrackingCategory();
    queryClient.setQueryData(trackingCommentsQueryKey("analysis-1", category.category_key), [
      {
        id: "comment-3",
        analysis_id: "analysis-1",
        version_id: "version-1",
        category_key: "objeto_alcance",
        scope: "category",
        content: "Comentario cerrado",
        created_by: "user-1",
        created_by_name: "Autora",
        created_at: "2026-08-19T12:30:00Z",
      },
    ] satisfies TrackingComment[]);

    render(
      <QueryClientProvider client={queryClient}>
        <TrackingCommentsPanel
          analysisId="analysis-1"
          category={category}
          isClosed
          isReadOnly
          onCreateComment={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(screen.queryByText(/modo solo lectura/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Agregar comentario" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Ver historial" }));
    expect(screen.queryByRole("button", { name: "Editar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Eliminar" })).not.toBeInTheDocument();
  });
});
