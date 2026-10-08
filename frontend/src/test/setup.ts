import "@testing-library/jest-dom";

// jsdom no implementa scrollIntoView; varios componentes lo llaman como efecto secundario.
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
