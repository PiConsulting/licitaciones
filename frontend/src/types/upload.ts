export const MAX_FILES = 10;
// MVP: el backend soporta multi-archivo (MAX_FILES) pero la UI por ahora solo
// deja subir uno. Subir el límite acá cuando se habilite multi-archivo en el
// producto — el resto del código (Step2DesignatePrimary, etc.) ya funciona.
export const MVP_MAX_FILES = 1;
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
