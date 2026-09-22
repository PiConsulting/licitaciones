import "@testing-library/jest-dom";

// jsdom doesn't implement scrollIntoView; several components call it as a side effect.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom no implementa ResizeObserver, usado por `useContainerWidth` para medir el panel del PDF.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as never);
