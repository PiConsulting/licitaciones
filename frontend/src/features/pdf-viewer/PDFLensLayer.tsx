import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Page } from "react-pdf";

import { HighlightOverlay, getCombinedHighlightRegions } from "../../utils/coordinateBasedHighlight";
import { createCitationTextRenderer } from "../../utils/highlightText";
import type { HighlightRegion } from "../analysis-detail/types";
import {
  LENS_DIMENSIONS,
  LENS_MAX_RENDER_SCALE,
  formatLensZoom,
  type LensConfig,
} from "./lens";

interface LensSource {
  page: number;
  highlight_regions?: HighlightRegion[];
}

interface LensPointer {
  page: number;
  x: number;
  y: number;
  clientX: number;
  clientY: number;
}

interface PDFLensLayerProps {
  containerRef: RefObject<HTMLElement | null>;
  config: LensConfig;
  displayScale: number;
  sources?: LensSource[];
  activeCitation: { page: number; text: string } | null;
  onZoomStep: (direction: 1 | -1) => void;
}

const BORDER_WIDTH = 3;

export function PDFLensLayer({
  containerRef,
  config,
  displayScale,
  sources,
  activeCitation,
  onZoomStep,
}: PDFLensLayerProps) {
  const [pointer, setPointer] = useState<LensPointer | null>(null);
  const onZoomStepRef = useRef(onZoomStep);
  onZoomStepRef.current = onZoomStep;

  useEffect(() => {
    const container = containerRef.current;
    if (!config.enabled || !container) {
      setPointer(null);
      return;
    }

    let frame = 0;
    let last: { x: number; y: number; target: EventTarget | null } | null = null;

    const compute = () => {
      frame = 0;
      if (!last) {
        return;
      }
      const hit = document.elementFromPoint?.(last.x, last.y) ?? last.target;
      const pageElement = hit instanceof Element ? hit.closest<HTMLElement>(".react-pdf__Page") : null;
      const pageNumber = Number(pageElement?.dataset.pageNumber);
      if (!pageElement || !Number.isFinite(pageNumber)) {
        setPointer(null);
        return;
      }
      const rect = pageElement.getBoundingClientRect();
      setPointer({
        page: pageNumber,
        x: last.x - rect.left,
        y: last.y - rect.top,
        clientX: last.x,
        clientY: last.y,
      });
    };

    const schedule = () => {
      if (!frame) {
        frame = requestAnimationFrame(compute);
      }
    };

    const handleMove = (event: MouseEvent) => {
      last = { x: event.clientX, y: event.clientY, target: event.target };
      schedule();
    };

    const handleLeave = () => {
      last = null;
      setPointer(null);
    };

    const handleScroll = () => {
      if (last) {
        schedule();
      }
    };

    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) {
        return;
      }
      event.preventDefault();
      onZoomStepRef.current(event.deltaY < 0 ? 1 : -1);
    };

    container.addEventListener("mousemove", handleMove);
    container.addEventListener("mouseleave", handleLeave);
    container.addEventListener("scroll", handleScroll);
    container.addEventListener("wheel", handleWheel, { passive: false });

    return () => {
      if (frame) {
        cancelAnimationFrame(frame);
      }
      container.removeEventListener("mousemove", handleMove);
      container.removeEventListener("mouseleave", handleLeave);
      container.removeEventListener("scroll", handleScroll);
      container.removeEventListener("wheel", handleWheel);
      setPointer(null);
    };
  }, [config.enabled, containerRef]);

  const pageNumber = pointer?.page ?? 0;

  const highlightRegions = useMemo(
    () => (sources && pageNumber ? getCombinedHighlightRegions(sources, pageNumber) : []),
    [sources, pageNumber],
  );

  const citationText = activeCitation && activeCitation.page === pageNumber ? activeCitation.text : null;
  const customTextRenderer = useMemo(
    () => createCitationTextRenderer(citationText ? [citationText] : []),
    [citationText],
  );

  if (!config.enabled || !pointer) {
    return null;
  }

  const container = containerRef.current;
  const [width, height] = LENS_DIMENSIONS[config.shape][config.size];
  const baseScale = displayScale > 0 ? displayScale : 1;
  const lensScale = Math.min(baseScale * config.zoom, LENS_MAX_RENDER_SCALE);
  const ratio = lensScale / baseScale;
  const left = pointer.clientX - width / 2;
  const top = pointer.clientY - height / 2;

  let clipPath: string | undefined;
  if (container) {
    const bounds = container.getBoundingClientRect();
    const insetTop = Math.max(0, bounds.top - top);
    const insetRight = Math.max(0, left + width - bounds.right);
    const insetBottom = Math.max(0, top + height - bounds.bottom);
    const insetLeft = Math.max(0, bounds.left - left);
    clipPath = `inset(${insetTop}px ${insetRight}px ${insetBottom}px ${insetLeft}px)`;
  }

  const useCoordinateHighlight = highlightRegions.length > 0;
  const showTextLayer = !useCoordinateHighlight && citationText !== null;

  return createPortal(
    <div
      data-testid="pdf-lens"
      aria-hidden="true"
      className={[
        "pointer-events-none fixed z-[70] isolate overflow-hidden border-[3px] border-[#0099DB] bg-white shadow-[0_14px_34px_rgba(0,60,107,.35),0_0_0_3px_rgba(255,255,255,.9)]",
        config.shape === "circ" ? "rounded-full" : "rounded-2xl",
      ].join(" ")}
      style={{ left, top, width, height, clipPath }}
    >
      <div
        className="absolute left-0 top-0"
        style={{
          transform: `translate(${width / 2 - BORDER_WIDTH - pointer.x * ratio}px, ${height / 2 - BORDER_WIDTH - pointer.y * ratio}px)`,
        }}
      >
        <div className="relative">
          <Page
            pageNumber={pageNumber}
            scale={lensScale}
            renderTextLayer={showTextLayer}
            renderAnnotationLayer={false}
            customTextRenderer={showTextLayer ? customTextRenderer : undefined}
          />
          {useCoordinateHighlight ? <HighlightOverlay regions={highlightRegions} scale={lensScale} /> : null}
        </div>
      </div>
      <span className="absolute left-1/2 top-1/2 z-[2] h-[14px] w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-[2px] bg-[rgba(0,153,219,.55)]" />
      <span className="absolute bottom-1.5 right-2 z-[2] rounded-full bg-[#003C6B] px-2 py-[2px] text-[10px] font-bold text-white">
        {formatLensZoom(config.zoom)}
      </span>
    </div>,
    document.body,
  );
}
