import { useCallback, useRef, useState } from "react";

/**
 * Measures an element's content-box width via ResizeObserver.
 *
 * Uses a callback ref (not `useRef` + a mount-time `useEffect`) on purpose:
 * PDFViewer only renders the measured `<div>` once its data has finished
 * loading, i.e. on a *later* render than the component's first mount. A
 * `useEffect(..., [])` reading `ref.current` would have already run against
 * `null` by the time that div appears and would never re-run, so `width`
 * would silently stay stuck at 0 forever. A callback ref fires exactly when
 * the DOM node itself is attached, whichever render that happens on.
 */
export function useContainerWidth<T extends HTMLElement>(): { ref: (node: T | null) => void; width: number } {
  const [width, setWidth] = useState(0);
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback((node: T | null) => {
    observerRef.current?.disconnect();
    observerRef.current = null;

    if (!node) {
      return;
    }

    setWidth(node.getBoundingClientRect().width);

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setWidth(entry.contentRect.width);
      }
    });
    observer.observe(node);
    observerRef.current = observer;
  }, []);

  return { ref, width };
}
