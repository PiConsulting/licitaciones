import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";

import { listTrackingComments } from "../../../api/tracking";
import type { TrackingCategory } from "../../../types/tracking";
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

function authorLabel(comment: { created_by_name?: string | null; created_by: string }): string {
  return (comment.created_by_name ?? "").trim() || comment.created_by;
}

function editorLabel(comment: { edited_by_name?: string | null; edited_by?: string | null }): string {
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
    <section aria-label={`Comentarios de seguimiento ${category.category_key}`}>
      <button
        type="button"
        className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-[#003C6B] hover:text-[#0099DB]"
        onClick={() => setShowHistory((current) => !current)}
        aria-expanded={showHistory}
        aria-controls={`tracking-comments-history-${category.category_key}`}
      >
        <span>Comentarios</span>
        <span className="text-xs text-[rgba(0,60,107,.55)]">({commentsCount})</span>
        {showHistory ? <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />}
      </button>

      {showHistory ? (
        <div id={`tracking-comments-history-${category.category_key}`} className="mt-2.5 flex flex-col gap-2.5">
          {!isReadOnly ? (
            <div className="flex items-center justify-end">
              <button
                type="button"
                disabled={isClosed || loading}
                onClick={() => setShowCommentForm((current) => !current)}
                className="inline-flex h-7 items-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3 text-xs font-semibold text-[#003C6B] transition-colors hover:border-[#0099DB] hover:text-[#0099DB] disabled:opacity-50"
              >
                {showCommentForm ? "Ocultar comentario" : "Agregar comentario"}
              </button>
            </div>
          ) : null}

          {showCommentForm ? (
            <div className="rounded-xl border border-[rgba(0,60,107,.12)] bg-[#F4F9FC] p-3">
              <label htmlFor={`tracking-comment-${category.category_key}`} className="mb-1 block text-xs font-semibold text-[#003C6B]">
                Nuevo comentario
              </label>
              <textarea
                id={`tracking-comment-${category.category_key}`}
                value={text}
                onChange={(event) => setText(event.target.value)}
                className="min-h-[80px] w-full rounded-lg border border-[rgba(0,60,107,.2)] bg-white px-2.5 py-2 text-sm text-[#003C6B]"
                disabled={isClosed || isReadOnly || loading}
              />

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={isClosed || isReadOnly || text.trim().length === 0 || loading}
                  onClick={async () => {
                    await onCreateComment({ content: text });
                    setText("");
                    setShowCommentForm(false);
                  }}
                  className="inline-flex h-8 items-center rounded-full bg-[#003C6B] px-3.5 text-xs font-semibold text-white transition-colors hover:bg-[#0099DB] disabled:opacity-50"
                >
                  Guardar comentario
                </button>
              </div>
            </div>
          ) : null}

          {!isReadOnly && isClosed ? (
            <p className="text-xs text-[rgba(0,60,107,.55)]">Reabrí la revisión para comentar.</p>
          ) : null}

          <div className="flex flex-col gap-2">
            {commentsQuery.isLoading ? <p className="text-xs text-[rgba(0,60,107,.55)]">Cargando comentarios...</p> : null}
            {!commentsQuery.isLoading && comments.length === 0 ? (
              <p className="text-xs text-[rgba(0,60,107,.55)]">Todavía no hay comentarios.</p>
            ) : null}
            {comments.map((comment) => (
              <div key={comment.id} className="rounded-xl border border-[rgba(0,60,107,.1)] bg-white px-3 py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[rgba(0,60,107,.55)]">
                  <span className="font-semibold text-[#003C6B]">{authorLabel(comment)}</span>
                  <span>{formatDateTime(comment.created_at)}</span>
                </div>
                {editingCommentId === comment.id ? (
                  <div className="mt-2">
                    <textarea
                      value={editingContent}
                      onChange={(event) => setEditingContent(event.target.value)}
                      className="min-h-[64px] w-full rounded-lg border border-[rgba(0,60,107,.2)] px-2.5 py-2 text-sm text-[#003C6B]"
                      disabled={loading}
                    />
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        type="button"
                        disabled={loading || editingContent.trim().length === 0}
                        onClick={async () => {
                          await onUpdateComment?.({ commentId: comment.id, content: editingContent });
                          setEditingCommentId(null);
                          setEditingContent("");
                        }}
                        className="inline-flex h-7 items-center rounded-full bg-[#003C6B] px-3 text-xs font-semibold text-white transition-colors hover:bg-[#0099DB] disabled:opacity-50"
                      >
                        Guardar edición
                      </button>
                      <button
                        type="button"
                        disabled={loading}
                        onClick={() => {
                          setEditingCommentId(null);
                          setEditingContent("");
                        }}
                        className="inline-flex h-7 items-center rounded-full px-3 text-xs font-semibold text-[rgba(0,60,107,.68)] hover:text-[#003C6B]"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="mt-1 text-sm text-[#003C6B]">{comment.content}</p>
                )}
                {comment.edited_at ? (
                  <p className="mt-1 text-[11px] text-[rgba(0,60,107,.55)]">
                    {comment.created_by !== comment.edited_by
                      ? `Editado por ${editorLabel(comment)} · ${formatDateTime(comment.edited_at)}`
                      : `Editado ${formatDateTime(comment.edited_at)}`}
                  </p>
                ) : null}
                {!isReadOnly && !isClosed && editingCommentId !== comment.id ? (
                  <div className="mt-2 flex items-center gap-3">
                    <button
                      type="button"
                      disabled={loading}
                      onClick={() => {
                        setEditingCommentId(comment.id);
                        setEditingContent(comment.content);
                      }}
                      className="text-xs font-semibold text-[#0099DB] hover:text-[#003C6B]"
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      disabled={loading}
                      onClick={async () => {
                        await onDeleteComment?.({ commentId: comment.id });
                      }}
                      className="text-xs font-semibold text-[#DC2626] hover:text-[#B91C1C]"
                    >
                      Eliminar
                    </button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
