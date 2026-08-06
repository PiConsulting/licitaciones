import "@testing-library/jest-dom";

// jsdom doesn't implement scrollIntoView; several components (PDFViewer,
// AnalysisSummaryStrip) call it as a side effect that tests don't assert on.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
