import { computePreviewCounts } from "./Step4StartAnalysis";

describe("computePreviewCounts", () => {
  test("cuenta estados desde preview_criterios como array backend", () => {
    const counts = computePreviewCounts({
      preview_criterios: [
        { extraction_status: "success" },
        { extraction_status: "success" },
        { extraction_status: "not_found" },
        { extraction_status: "failed" },
        { extraction_status: "partial" },
      ],
    });

    expect(counts).toEqual({ found: 2, notFound: 2, review: 1 });
  });

  test("cuenta estados desde preview_criterios normalizado con items", () => {
    const counts = computePreviewCounts({
      preview_criterios: {
        items: [
          { extraction_status: "success" },
          { extraction_status: "partial" },
          { extraction_status: "partial" },
        ],
      },
    });

    expect(counts).toEqual({ found: 1, notFound: 0, review: 2 });
  });

  test("devuelve ceros si no hay preview_criterios", () => {
    const counts = computePreviewCounts(null);

    expect(counts).toEqual({ found: 0, notFound: 0, review: 0 });
  });
});
