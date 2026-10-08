import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Ban, Check, ChevronDown, MessageCircle, X } from "lucide-react";

import { listTrackingComments } from "../../api/tracking";
import { CATEGORY_NAMES } from "../../utils/categoryIcons";
import type { CategoryData, CategoryId } from "../analysis-detail/types";
import type { TrackingCategory, TrackingComment, TrackingItem, TrackingItemStatus } from "../../types/tracking";
import { trackingItemCommentsQueryKey } from "../analysis-detail/hooks/useTrackingMutations";
import { buildChecklistItemContents } from "./buildChecklistItems";
import { ItemCommentComposer, ItemCommentsList } from "./ChecklistItemComments";

const STATUS_OPTIONS: Array<{
  value: TrackingItemStatus;
  title: string;
  icon: typeof Check;
  activeBg: string;
  activeFg: string;
  hoverBg: string;
}> = [
  { value: "compliant", title: "Cumple", icon: Check, activeBg: "#1FC9A8", activeFg: "#003C6B", hoverBg: "rgba(31,201,168,.25)" },
  { value: "non_compliant", title: "No cumple", icon: X, activeBg: "#DC2626", activeFg: "#fff", hoverBg: "rgba(220,38,38,.15)" },
  { value: "not_applicable", title: "No aplica", icon: Ban, activeBg: "#003C6B", activeFg: "#fff", hoverBg: "rgba(0,60,107,.15)" },
];

function formatUpdated(value?: string | null): string {
  if (!value) {
    return "sin revisar";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "sin revisar";
  }
  return new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit" }).format(date);
}

interface ChecklistItemRowProps {
  label: string;
  text: string;
  page: number | null;
  item: TrackingItem;
  comments: TrackingComment[];
  disabled: boolean;
  actionLoading: boolean;
  onChangeStatus: (trackingItemId: string, status: TrackingItemStatus) => void;
  onCreateComment: (trackingItemId: string, content: string) => Promise<void>;
  onUpdateComment: (commentId: string, content: string) => Promise<void>;
  onDeleteComment: (commentId: string) => Promise<void>;
}

function ChecklistItemRow({
  label,
  text,
  page,
  item,
  comments,
  disabled,
  actionLoading,
  onChangeStatus,
  onCreateComment,
  onUpdateComment,
  onDeleteComment,
}: ChecklistItemRowProps) {
  const [composerOpen, setComposerOpen] = useState(false);

  return (
    <div
      className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-5 gap-y-3 border-b border-[rgba(0,60,107,.06)] px-5 py-3.5 pl-[68px] last:border-b-0 ${
        item.status === "non_compliant" ? "bg-[rgba(220,38,38,.04)]" : "bg-white"
      }`}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-[#003C6B]">{label}</span>
          {page !== null ? (
            <span
              title="Referencia en el pliego"
              className="inline-flex h-[22px] items-center gap-1 rounded-full border border-[rgba(0,60,107,.12)] bg-white px-2 text-[11px] font-semibold text-[#0099DB]"
            >
              {`pág. ${page}`}
            </span>
          ) : null}
        </div>
        {text ? <p className="text-[13px] leading-normal text-[rgba(0,60,107,.68)]">{text}</p> : null}
        <ItemCommentsList
          comments={comments}
          canWrite={!disabled}
          loading={actionLoading}
          onUpdate={onUpdateComment}
          onDelete={onDeleteComment}
        />
        {composerOpen && !disabled ? (
          <ItemCommentComposer
            itemLabel={label}
            loading={actionLoading}
            onCreate={(content) => onCreateComment(item.tracking_item_id, content)}
            onClose={() => setComposerOpen(false)}
          />
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        <div
          role="group"
          aria-label={`Estado del ítem: ${label}`}
          className="inline-flex gap-0.5 rounded-full bg-[rgba(0,60,107,.06)] p-[3px]"
        >
          {STATUS_OPTIONS.map((option) => {
            const Icon = option.icon;
            const isActive = item.status === option.value;
            return (
              <button
                key={option.value}
                type="button"
                disabled={disabled}
                aria-pressed={isActive}
                aria-label={`${option.title}: ${label}`}
                title={option.title}
                onClick={() => onChangeStatus(item.tracking_item_id, isActive ? "not_evaluated" : option.value)}
                className="flex h-[34px] w-[34px] items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                style={{
                  backgroundColor: isActive ? option.activeBg : "transparent",
                  color: isActive ? option.activeFg : "rgba(0,60,107,.5)",
                }}
                onMouseEnter={(event) => {
                  if (!isActive && !disabled) {
                    event.currentTarget.style.backgroundColor = option.hoverBg;
                  }
                }}
                onMouseLeave={(event) => {
                  if (!isActive) {
                    event.currentTarget.style.backgroundColor = "transparent";
                  }
                }}
              >
                <Icon className="h-4 w-4" strokeWidth={2.5} aria-hidden="true" />
              </button>
            );
          })}
        </div>
        <button
          type="button"
          disabled={disabled}
          aria-label={`Comentar: ${label}`}
          aria-expanded={composerOpen}
          title="Comentar"
          onClick={() => setComposerOpen((current) => !current)}
          className={`inline-flex h-[34px] w-[34px] items-center justify-center rounded-full border-[1.5px] bg-white transition-colors hover:border-[#0099DB] hover:text-[#0099DB] disabled:cursor-not-allowed disabled:opacity-50 ${
            composerOpen ? "border-[#0099DB] text-[#0099DB]" : "border-[rgba(0,60,107,.15)] text-[rgba(0,60,107,.55)]"
          }`}
        >
          <MessageCircle className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

interface ChecklistCategoryCardProps {
  analysisId: string;
  categoryId: CategoryId;
  category: CategoryData;
  trackingCategory: TrackingCategory;
  isOpen: boolean;
  readOnly: boolean;
  actionLoading: boolean;
  onToggleOpen: () => void;
  onToggleClosed: () => void;
  onChangeItemStatus: (trackingItemId: string, status: TrackingItemStatus) => void;
  onCreateComment: (trackingItemId: string, content: string) => Promise<void>;
  onUpdateComment: (commentId: string, content: string) => Promise<void>;
  onDeleteComment: (commentId: string) => Promise<void>;
}

export function ChecklistCategoryCard({
  analysisId,
  categoryId,
  category,
  trackingCategory,
  isOpen,
  readOnly,
  actionLoading,
  onToggleOpen,
  onToggleClosed,
  onChangeItemStatus,
  onCreateComment,
  onUpdateComment,
  onDeleteComment,
}: ChecklistCategoryCardProps) {
  const commentsQuery = useQuery({
    queryKey: trackingItemCommentsQueryKey(analysisId, categoryId),
    queryFn: () => listTrackingComments(analysisId, categoryId, { scope: "checklist_item" }),
    enabled: isOpen,
  });
  const commentsByItem = new Map<string, TrackingComment[]>();
  for (const comment of commentsQuery.data ?? []) {
    if (comment.tracking_item_id) {
      commentsByItem.set(comment.tracking_item_id, [...(commentsByItem.get(comment.tracking_item_id) ?? []), comment]);
    }
  }
  const name = CATEGORY_NAMES[categoryId];
  const items = buildChecklistItemContents(category, categoryId, trackingCategory.items);
  const total = trackingCategory.items.length;
  const ok = trackingCategory.items.filter((item) => item.status === "compliant").length;
  const no = trackingCategory.items.filter((item) => item.status === "non_compliant").length;
  const na = trackingCategory.items.filter((item) => item.status === "not_applicable").length;
  const commentsTotal = trackingCategory.items.reduce((sum, item) => sum + (item.comments_count ?? 0), 0);
  const done = ok + no + na;
  const closed = trackingCategory.status === "closed";
  const started = done > 0;
  const isDisabled = readOnly || closed;

  const stLabel = closed ? "Cerrada" : trackingCategory.status === "in_review" ? "En revisión" : "Sin revisar";
  const stBg = closed ? "rgba(127,243,222,.35)" : started ? "rgba(0,153,219,.12)" : "rgba(0,60,107,.08)";
  const stFg = closed ? "#0B6B58" : started ? "#0077AD" : "rgba(0,60,107,.68)";
  const ringBg = closed ? "#1FC9A8" : started ? "#F4F9FC" : "rgba(0,60,107,.06)";
  const ringFg = closed ? "#003C6B" : started ? "#003C6B" : "rgba(0,60,107,.55)";
  const borderColor = closed ? "rgba(31,201,168,.5)" : no > 0 ? "rgba(220,38,38,.35)" : "rgba(0,60,107,.12)";
  const footer =
    done === total
      ? "Todos los ítems evaluados."
      : `${total - done} ítem${total - done === 1 ? "" : "s"} sin evaluar. Se puede cerrar igual; queda registrado.`;

  return (
    <article className="overflow-hidden rounded-2xl border bg-white" style={{ borderColor }} data-testid="checklist-category-card">
      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-3.5 px-5 py-3.5 text-left transition-colors hover:bg-[#F4F9FC]"
      >
        <span
          className="flex h-[34px] w-[34px] flex-shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: ringBg, color: ringFg }}
        >
          {closed ? (
            <Check className="h-4 w-4" strokeWidth={3} aria-hidden="true" />
          ) : (
            <span className="font-display text-xs font-bold">{`${done}/${total}`}</span>
          )}
        </span>

        <div className="flex flex-1 flex-wrap items-center gap-2">
          <h2 className="font-display text-base font-semibold text-[#003C6B]">{name}</h2>
          <span
            className="inline-flex rounded-full px-2.5 py-[3px] text-[11px] font-bold"
            style={{ backgroundColor: stBg, color: stFg }}
          >
            {stLabel}
          </span>
          {no > 0 ? (
            <span className="inline-flex rounded-full bg-[#FEE2E2] px-2.5 py-[3px] text-[11px] font-bold text-[#DC2626]">
              {`${no} no cumple`}
            </span>
          ) : null}
          {commentsTotal > 0 ? (
            <span
              data-testid="category-comments-badge"
              className="inline-flex items-center gap-1 rounded-full bg-[rgba(0,153,219,.12)] px-2.5 py-[3px] text-[11px] font-bold text-[#0077AD]"
            >
              <MessageCircle className="h-3 w-3" strokeWidth={2.25} aria-hidden="true" />
              {`${commentsTotal} ${commentsTotal === 1 ? "comentario" : "comentarios"}`}
            </span>
          ) : null}
        </div>

        <div className="flex flex-shrink-0 items-center gap-3.5">
          <div className="flex h-1.5 w-[120px] overflow-hidden rounded-full bg-[rgba(0,60,107,.1)]">
            <div className="h-full bg-[#1FC9A8]" style={{ width: `${total > 0 ? (ok / total) * 100 : 0}%` }} />
            <div className="h-full bg-[#DC2626]" style={{ width: `${total > 0 ? (no / total) * 100 : 0}%` }} />
            <div className="h-full bg-[rgba(0,60,107,.3)]" style={{ width: `${total > 0 ? (na / total) * 100 : 0}%` }} />
          </div>
          <span className="whitespace-nowrap text-xs text-[rgba(0,60,107,.55)]">
            {closed ? `cerrada · ${formatUpdated(trackingCategory.updated_at)}` : formatUpdated(trackingCategory.updated_at)}
          </span>
          <ChevronDown
            className={`h-[18px] w-[18px] text-[rgba(0,60,107,.45)] transition-transform ${isOpen ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </div>
      </button>

      {isOpen ? (
        <div className="border-t border-[rgba(0,60,107,.08)]">
          {items.map(({ trackingItem, label, text, page }) => (
            <ChecklistItemRow
              key={trackingItem.tracking_item_id}
              label={label}
              text={text}
              page={page}
              item={trackingItem}
              comments={commentsByItem.get(trackingItem.tracking_item_id) ?? []}
              disabled={isDisabled}
              actionLoading={actionLoading}
              onChangeStatus={onChangeItemStatus}
              onCreateComment={onCreateComment}
              onUpdateComment={onUpdateComment}
              onDeleteComment={onDeleteComment}
            />
          ))}

          <div className="flex flex-wrap items-center justify-between gap-3 bg-white px-5 py-3.5 pl-[68px]">
            <span className="text-xs text-[rgba(0,60,107,.55)]">{footer}</span>
            {!readOnly ? (
              <button
                type="button"
                disabled={actionLoading}
                onClick={onToggleClosed}
                className={`inline-flex h-[34px] items-center gap-2 rounded-full px-4 text-[13px] font-semibold transition-colors disabled:opacity-50 ${
                  closed
                    ? "border-[1.5px] border-[rgba(0,60,107,.2)] bg-white text-[#003C6B] hover:border-[#0099DB]"
                    : "bg-[#003C6B] text-white hover:bg-[#0099DB]"
                }`}
              >
                {closed ? "Reabrir categoría" : "Cerrar categoría"}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </article>
  );
}
