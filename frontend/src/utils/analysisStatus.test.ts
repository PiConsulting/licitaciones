import { describe, expect, test } from "vitest";

import { isRunningAnalysisStatus } from "./analysisStatus";

describe("isRunningAnalysisStatus", () => {
  test("considera 'processing' como en curso (bug 2026-09-29: el polling del Home se cortaba acá)", () => {
    expect(isRunningAnalysisStatus("processing")).toBe(true);
  });

  test("considera 'queued' como en curso", () => {
    expect(isRunningAnalysisStatus("queued")).toBe(true);
  });

  test("no considera en curso los estados terminales ni el legacy 'analyzing' (nunca fue un status real, solo lo usaba un stub muerto)", () => {
    expect(isRunningAnalysisStatus("draft")).toBe(false);
    expect(isRunningAnalysisStatus("analyzed")).toBe(false);
    expect(isRunningAnalysisStatus("en_revision")).toBe(false);
    expect(isRunningAnalysisStatus("error")).toBe(false);
    expect(isRunningAnalysisStatus("cancelled")).toBe(false);
    expect(isRunningAnalysisStatus("analyzing")).toBe(false);
  });
});
