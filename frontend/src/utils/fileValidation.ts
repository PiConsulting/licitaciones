import {
  MAX_FILES,
  MAX_FILE_SIZE_BYTES,
  MAX_TOTAL_SIZE_BYTES,
  type ValidationResult,
} from "../types/upload";

function formatMb(bytes: number): string {
  return (bytes / (1024 * 1024)).toFixed(2);
}

export function validateFileFormat(file: File): ValidationResult {
  if (file.type === "application/pdf") {
    return { valid: true };
  }

  return {
    valid: false,
    error: `«${file.name}» no es un PDF. El sistema sólo analiza archivos PDF; convertí el documento antes de subirlo`,
  };
}

export function validateFileSize(file: File): ValidationResult {
  if (file.size <= MAX_FILE_SIZE_BYTES) {
    return { valid: true };
  }

  return {
    valid: false,
    error: `«${file.name}» pesa ${formatMb(file.size)} MB y el máximo por archivo es 50 MB. Probá comprimirlo o dividirlo`,
  };
}

export function validateTotalSize(totalBytes: number): ValidationResult {
  if (totalBytes <= MAX_TOTAL_SIZE_BYTES) {
    return { valid: true };
  }

  return {
    valid: false,
    error: `Los archivos seleccionados suman ${formatMb(totalBytes)} MB y el máximo por análisis es 150 MB. Quitá alguno o analizalos en dos tandas`,
  };
}

export function validateFileCount(count: number): ValidationResult {
  if (count <= MAX_FILES) {
    return { valid: true };
  }

  return {
    valid: false,
    error: `Podés subir hasta 10 archivos por análisis y seleccionaste ${count}`,
  };
}

export function formatFileSizeMb(bytes: number): string {
  return formatMb(bytes);
}
