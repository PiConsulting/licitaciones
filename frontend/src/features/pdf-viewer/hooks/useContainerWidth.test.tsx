import { act, render } from "@testing-library/react";

import { useContainerWidth } from "./useContainerWidth";

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    FakeResizeObserver.instances.push(this);
  }

  observe() {}
  unobserve() {}
  disconnect() {}

  trigger(width: number) {
    this.callback([{ contentRect: { width } } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
}

function TestComponent({ onWidthChange }: { onWidthChange: (width: number) => void }) {
  const { ref, width } = useContainerWidth<HTMLDivElement>();
  onWidthChange(width);
  return <div ref={ref} data-testid="measured" />;
}

describe("useContainerWidth", () => {
  beforeEach(() => {
    FakeResizeObserver.instances = [];
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  });

  test("empieza en 0 antes de recibir ninguna medición", () => {
    let latestWidth = -1;
    render(<TestComponent onWidthChange={(width) => (latestWidth = width)} />);

    expect(latestWidth).toBe(0);
  });

  test("actualiza el ancho cuando ResizeObserver reporta un nuevo contentRect", () => {
    let latestWidth = -1;
    render(<TestComponent onWidthChange={(width) => (latestWidth = width)} />);

    const observerInstance = FakeResizeObserver.instances[FakeResizeObserver.instances.length - 1];
    act(() => {
      observerInstance?.trigger(480);
    });

    expect(latestWidth).toBe(480);
  });
});
