import { describe, expect, test } from "vitest";

import {
  formatFileSizeMb,
  validateFileCount,
  validateFileFormat,
  validateFileSize,
  validateTotalSize,
} from "./fileValidation";

function createMockFile(name: string, type: string, size: number): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("fileValidation", () => {
  test("valida formato PDF", () => {
    const validFile = createMockFile("ok.pdf", "application/pdf", 1024);
    const invalidFile = createMockFile(
      "test.docx",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      1024,
    );

    expect(validateFileFormat(validFile)).toEqual({ valid: true });
    expect(validateFileFormat(invalidFile)).toEqual({
      valid: false,
      error:
        "«test.docx» no es un PDF. El sistema sólo analiza archivos PDF; convertí el documento antes de subirlo",
    });
  });

  test("valida tamaño individual <=50MB", () => {
    const validFile = createMockFile("ok.pdf", "application/pdf", 50 * 1024 * 1024);
    const invalidFile = createMockFile("big.pdf", "application/pdf", 60 * 1024 * 1024);

    expect(validateFileSize(validFile)).toEqual({ valid: true });
    expect(validateFileSize(invalidFile).valid).toBe(false);
  });

  test("valida tamaño total <=150MB", () => {
    const result = validateTotalSize(160 * 1024 * 1024);

    expect(result.valid).toBe(false);
    expect(result.error).toContain("160.00 MB");
  });

  test("valida cantidad <=10", () => {
    const result = validateFileCount(11);

    expect(result.valid).toBe(false);
    expect(result.error).toContain("11");
  });

  test("formatea tamaño en MB", () => {
    expect(formatFileSizeMb(10 * 1024 * 1024)).toBe("10.00");
  });
});
