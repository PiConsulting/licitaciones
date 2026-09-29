import { useState } from "react";
import { MessageCircle } from "lucide-react";

import type { TrackingComment } from "../../types/tracking";

interface ItemCommentsListProps {
  comments: TrackingComment[];
  canWrite: boolean;
  loading: boolean;
  onUpdate: (commentId: string, content: string) => Promise<void>;
  onDelete: (commentId: string) => Promise<void>;
}

export function ItemCommentsList({ comments, canWrite, loading, onUpdate, onDelete }: ItemCommentsListProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");

  return (
    <>
      {comments.map((comment) => (
        <div
          key={comment.id}
          className="mt-1 flex items-start gap-2 rounded-[10px] bg-[#F4F9FC] px-3 py-2 text-xs leading-[1.5] text-[#003C6B]"
        >
          <MessageCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[#0099DB]" strokeWidth={2} aria-hidden="true" />
          {editingId === comment.id ? (
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <textarea
                aria-label="Editar comentario"
                value={editingText}
                onChange={(event) => setEditingText(event.target.value)}
                disabled={loading}
                className="min-h-[56px] w-full rounded-[10px] border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3 py-2 text-xs text-[#003C6B]"
              />
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  disabled={loading || editingText.trim().length === 0}
                  onClick={async () => {
                    await onUpdate(comment.id, editingText);
                    setEditingId(null);
                    setEditingText("");
                  }}
                  className="inline-flex h-8 items-center rounded-full bg-[#003C6B] px-4 text-xs font-semibold text-white transition-colors hover:bg-[#0099DB] disabled:opacity-50"
                >
                  Guardar edición
                </button>
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => {
                    setEditingId(null);
                    setEditingText("");
                  }}
                  className="text-xs font-semibold text-[rgba(0,60,107,.68)] hover:text-[#003C6B]"
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <div className="min-w-0 flex-1">
              <span>
                <strong className="font-semibold">{(comment.created_by_name ?? "").trim() || comment.created_by}</strong>
                {` · ${comment.content}`}
              </span>
              {canWrite ? (
                <span className="ml-2 inline-flex items-center gap-2 whitespace-nowrap align-baseline">
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => {
                      setEditingId(comment.id);
                      setEditingText(comment.content);
                    }}
                    className="text-[11px] font-semibold text-[#0099DB] hover:text-[#003C6B]"
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => {
                      void onDelete(comment.id);
                    }}
                    className="text-[11px] font-semibold text-[rgba(0,60,107,.55)] hover:text-[#DC2626]"
                  >
                    Eliminar
                  </button>
                </span>
              ) : null}
            </div>
          )}
        </div>
      ))}
    </>
  );
}

interface ItemCommentComposerProps {
  itemLabel: string;
  loading: boolean;
  onCreate: (content: string) => Promise<void>;
  onClose: () => void;
}

export function ItemCommentComposer({ itemLabel, loading, onCreate, onClose }: ItemCommentComposerProps) {
  const [text, setText] = useState("");

  return (
    <div className="mt-1 flex flex-col gap-2 rounded-[10px] bg-[#F4F9FC] p-3">
      <textarea
        aria-label={`Nuevo comentario: ${itemLabel}`}
        placeholder="Escribí un comentario sobre este ítem"
        value={text}
        onChange={(event) => setText(event.target.value)}
        disabled={loading}
        className="min-h-[64px] w-full rounded-[10px] border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3 py-2 text-xs text-[#003C6B] placeholder:text-[rgba(0,60,107,.45)] focus:border-[#0099DB] focus:outline-none"
      />
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={loading || text.trim().length === 0}
          onClick={async () => {
            await onCreate(text);
            setText("");
            onClose();
          }}
          className="inline-flex h-8 items-center rounded-full bg-[#003C6B] px-4 text-xs font-semibold text-white transition-colors hover:bg-[#0099DB] disabled:opacity-50"
        >
          Guardar comentario
        </button>
        <button
          type="button"
          onClick={onClose}
          className="text-xs font-semibold text-[rgba(0,60,107,.68)] hover:text-[#003C6B]"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}
