import "@testing-library/jest-dom";

// jsdom doesn't implement scrollIntoView; several components (PDFViewer,
// AnalysisSummaryStrip) call it as a side effect that tests don't assert on.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}


// jsdom no implementa ResizeObserver, que usa `useContainerWidth` para medir el
// ancho del panel del PDF.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (ResizeObserverStub as never);
