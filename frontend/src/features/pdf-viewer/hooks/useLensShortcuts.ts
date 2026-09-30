import { useEffect } from "react";

interface UseLensShortcutsParams {
  enabled: boolean;
  paused?: boolean;
  onToggle: () => void;
  onExit: () => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function useLensShortcuts({ enabled, paused = false, onToggle, onExit }: UseLensShortcutsParams) {
  useEffect(() => {
    if (paused) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (enabled) {
          onExit();
        }
        return;
      }
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if ((event.key === "l" || event.key === "L") && !isEditableTarget(event.target)) {
        onToggle();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [enabled, paused, onToggle, onExit]);
}
