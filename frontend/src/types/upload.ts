export const MAX_FILES = 10;
export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
export const MAX_TOTAL_SIZE_BYTES = 150 * 1024 * 1024;

export type UploadFileStatus = "validating" | "valid";

export interface UploadedFile {
  id: string;
  file: File;
  sizeMb: string;
  pagesLabel: string;
  status: UploadFileStatus;
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
}
