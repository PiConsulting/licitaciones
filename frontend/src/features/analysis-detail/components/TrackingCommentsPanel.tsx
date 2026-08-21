import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";

import { listTrackingComments } from "../../../api/tracking";
import { Button } from "../../../components/Button";
import type { TrackingCategory, TrackingComment } from "../../../types/tracking";
import { trackingCommentsQueryKey } from "../hooks/useTrackingMutations";

interface TrackingCommentsPanelProps {
  analysisId?: string;
  category: TrackingCategory;
  isClosed: boolean;
  isReadOnly?: boolean;
  onCreateComment: (payload: { content: string }) => Promise<void>;
  onUpdateComment?: (payload: { commentId: string; content: string }) => Promise<void>;
  onDeleteComment?: (payload: { commentId: string }) => Promise<void>;
  loading?: boolean;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Fecha no disponible";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function scopeLabel(_comment: TrackingComment): string {
  return "Categoría";
}

function authorLabel(comment: TrackingComment): string {
  return (comment.created_by_name ?? "").trim() || comment.created_by;
}

function editorLabel(comment: TrackingComment): string {
  return (comment.edited_by_name ?? "").trim() || (comment.edited_by ?? "").trim();
}

export function TrackingCommentsPanel({
  analysisId = "",
  category,
  isClosed,
  isReadOnly = false,
  onCreateComment,
  onUpdateComment,
  onDeleteComment,
  loading = false,
}: TrackingCommentsPanelProps) {
  const [text, setText] = useState("");
  const [showCommentForm, setShowCommentForm] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState("");

  const commentsQuery = useQuery({
    queryKey: trackingCommentsQueryKey(analysisId, category.category_key),
    queryFn: () => listTrackingComments(analysisId, category.category_key),
    enabled: showHistory && analysisId.length > 0,
  });
  const comments = commentsQuery.data ?? [];
  const commentsCount = commentsQuery.data?.length ?? category.comments_count;

  return (
    <section className="mt-3" aria-label={`Comentarios de seguimiento ${category.category_key}`}>
      <button
        type="button"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900"
        onClick={() => setShowHistory((current) => !current)}
        aria-expanded={showHistory}
        aria-controls={`tracking-comments-history-${category.category_key}`}
      >
        <span>Comentarios</span>
        <span className="text-[11px] text-gray-500">({commentsCount})</span>
        {showHistory ? <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
      </button>

      {showHistory ? (
        <div id={`tracking-comments-history-${category.category_key}`} className="mt-2 space-y-2 pl-1">
          {!isReadOnly ? (
            <div className="flex items-center justify-end">
              <Button
                size="sm"
                variant="ghost"
                disabled={isClosed || loading}
                onClick={() => setShowCommentForm((current) => !current)}
              >
                {showCommentForm ? "Ocultar comentario" : "Agregar comentario"}
              </Button>
            </div>
          ) : null}

          {showCommentForm ? (
            <div className="rounded border border-gray-200 bg-white p-2.5">
              <label htmlFor={`tracking-comment-${category.category_key}`} className="mb-1 block text-xs font-medium text-gray-700">
                Nuevo comentario
              </label>
              <textarea
                id={`tracking-comment-${category.category_key}`}
                value={text}
                onChange={(event) => setText(event.target.value)}
                className="min-h-[80px] w-full rounded border border-gray-300 px-2 py-1 text-sm"
                disabled={isClosed || isReadOnly || loading}
              />

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={isClosed || isReadOnly || text.trim().length === 0}
                  loading={loading}
                  onClick={async () => {
                    await onCreateComment({ content: text });
                    setText("");
                    setShowCommentForm(false);
                  }}
                >
                  Guardar comentario
                </Button>
              </div>
            </div>
          ) : null}

          {!isReadOnly && isClosed ? <p className="mt-2 text-xs text-gray-500">Reabrí la revisión para comentar.</p> : null}

          <div className="space-y-2">
          {commentsQuery.isLoading ? <p className="mt-2 text-xs text-gray-500">Cargando comentarios...</p> : null}
          {!commentsQuery.isLoading && comments.length === 0 ? (
            <p className="mt-2 text-xs text-gray-500">Todavía no hay comentarios.</p>
          ) : null}
          {comments.length > 0 ? (
            <ul className="mt-2 space-y-2">
              {comments.map((comment) => (
                <li key={comment.id} className="border-l-2 border-gray-200 bg-white px-2 py-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-gray-500">
                    <span className="font-semibold text-gray-700">{scopeLabel(comment)}</span>
                    <span>{formatDateTime(comment.created_at)}</span>
                  </div>
                  {editingCommentId === comment.id ? (
                    <div className="mt-2">
                      <textarea
                        value={editingContent}
                        onChange={(event) => setEditingContent(event.target.value)}
                        className="min-h-[64px] w-full rounded border border-gray-300 px-2 py-1 text-sm"
                        disabled={loading}
                      />
                      <div className="mt-2 flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={loading || editingContent.trim().length === 0}
                          onClick={async () => {
                            await onUpdateComment?.({ commentId: comment.id, content: editingContent });
                            setEditingCommentId(null);
                            setEditingContent("");
                          }}
                        >
                          Guardar edición
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={loading}
                          onClick={() => {
                            setEditingCommentId(null);
                            setEditingContent("");
                          }}
                        >
                          Cancelar
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-1 text-sm text-gray-800">{comment.content}</p>
                  )}
                  <p className="mt-1 text-[11px] text-gray-500">{`Creado por ${authorLabel(comment)}`}</p>
                  {comment.edited_at ? (
                    <p className="mt-1 text-[11px] text-gray-500">
                      {comment.created_by !== comment.edited_by
                        ? `Editado por ${editorLabel(comment)} · ${formatDateTime(comment.edited_at)}`
                        : `Editado ${formatDateTime(comment.edited_at)}`}
                    </p>
                  ) : null}
                  {!isReadOnly && !isClosed && editingCommentId !== comment.id ? (
                    <div className="mt-2 flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={loading}
                        onClick={() => {
                          setEditingCommentId(comment.id);
                          setEditingContent(comment.content);
                        }}
                      >
                        Editar
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={loading}
                        onClick={async () => {
                          await onDeleteComment?.({ commentId: comment.id });
                        }}
                      >
                        Eliminar
                      </Button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      ) : null}
    </section>
  );
}
