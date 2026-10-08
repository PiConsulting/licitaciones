import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ZoomIn } from "lucide-react";

import {
  LENS_ZOOMS,
  formatLensZoom,
  type LensConfig,
  type LensShape,
  type LensSize,
} from "./lens";

interface PDFLensControlsProps {
  config: LensConfig;
  onToggle: () => void;
  onChange: (patch: Partial<Omit<LensConfig, "enabled">>) => void;
}

const SHAPE_OPTIONS: Array<{ value: LensShape; label: string }> = [
  { value: "rect", label: "Franja" },
  { value: "circ", label: "Círculo" },
];

const SIZE_OPTIONS: Array<{ value: LensSize; label: string }> = [
  { value: "s", label: "S" },
  { value: "m", label: "M" },
  { value: "l", label: "L" },
];

function segmentClass(active: boolean): string {
  return [
    "h-[30px] flex-1 cursor-pointer rounded-full border-[1.5px] text-xs font-bold",
    active
      ? "border-[#003C6B] bg-[#003C6B] text-white"
      : "border-[rgba(0,60,107,.2)] bg-white text-[#003C6B]",
  ].join(" ");
}

const SECTION_TITLE_CLASS =
  "mb-2 text-[11px] font-bold uppercase tracking-[.12em] text-[rgba(0,60,107,.55)]";

const MENU_WIDTH = 230;
const MENU_MARGIN = 8;

interface MenuPosition {
  left: number;
  top: number;
}

const KBD_CLASS =
  "rounded border border-[rgba(0,60,107,.2)] bg-[#F4F9FC] px-1 text-[10.5px]";

export function PDFLensControls({ config, onToggle, onChange }: PDFLensControlsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<MenuPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!menuOpen) {
      setMenuPosition(null);
      return;
    }
    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) {
        return;
      }
      const rect = trigger.getBoundingClientRect();
      const maxLeft = window.innerWidth - MENU_WIDTH - MENU_MARGIN;
      const left = Math.max(MENU_MARGIN, Math.min(rect.right - MENU_WIDTH, maxLeft));
      setMenuPosition({ left, top: rect.bottom + MENU_MARGIN });
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && (menuRef.current?.contains(target) || triggerRef.current?.contains(target))) {
        return;
      }
      setMenuOpen(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [menuOpen]);

  return (
    <div className="flex items-center gap-0.5 [@media(pointer:coarse)]:hidden">
      <span className="mx-1 h-[18px] w-px bg-[rgba(0,60,107,.2)]" aria-hidden="true" />
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={config.enabled}
        aria-label="Lupa"
        title="Lupa (L)"
        className={[
          "flex h-[30px] w-[30px] items-center justify-center rounded-lg text-[#003C6B] transition-colors",
          config.enabled ? "bg-[#003C6B] text-white shadow-[0_0_0_3px_rgba(0,153,219,.25)]" : "hover:bg-white",
        ].join(" ")}
      >
        <ZoomIn className="h-4 w-4" />
      </button>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setMenuOpen((open) => !open)}
        aria-expanded={menuOpen}
        aria-label="Opciones de lupa"
        title="Opciones de lupa"
        className="flex h-[30px] w-5 items-center justify-center rounded-lg text-[#003C6B] transition-colors hover:bg-white"
      >
        <ChevronDown className="h-4 w-4" />
      </button>

      {menuOpen && menuPosition
        ? createPortal(
        <div
          ref={menuRef}
          role="group"
          aria-label="Opciones de lupa"
          style={{ left: menuPosition.left, top: menuPosition.top, width: MENU_WIDTH }}
          className="fixed z-[80] rounded-[14px] border-[1.5px] border-[rgba(0,60,107,.12)] bg-white p-3 shadow-[0_12px_32px_rgba(0,60,107,.18)]"
        >
          <h4 className={SECTION_TITLE_CLASS}>Aumento</h4>
          <div className="mb-3 flex gap-1.5">
            {LENS_ZOOMS.map((zoom) => (
              <button
                key={zoom}
                type="button"
                aria-pressed={config.zoom === zoom}
                onClick={() => onChange({ zoom })}
                className={segmentClass(config.zoom === zoom)}
              >
                {formatLensZoom(zoom)}
              </button>
            ))}
          </div>

          <h4 className={SECTION_TITLE_CLASS}>Forma</h4>
          <div className="mb-3 flex gap-1.5">
            {SHAPE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={config.shape === option.value}
                onClick={() => onChange({ shape: option.value })}
                className={segmentClass(config.shape === option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>

          <h4 className={SECTION_TITLE_CLASS}>Tamaño</h4>
          <div className="mb-3 flex gap-1.5">
            {SIZE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={config.size === option.value}
                onClick={() => onChange({ size: option.value })}
                className={segmentClass(config.size === option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>

          <p className="m-0 text-[11px] leading-[1.4] text-[rgba(0,60,107,.55)]">
            <kbd className={KBD_CLASS}>L</kbd> activa/desactiva · <kbd className={KBD_CLASS}>Ctrl</kbd> + rueda
            cambia el aumento · <kbd className={KBD_CLASS}>Esc</kbd> sale
          </p>
        </div>,
        document.body,
      )
        : null}
    </div>
  );
}
