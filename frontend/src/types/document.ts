export interface DocumentResponse {
  id: string;
  filename: string;
  page_count: number;
  file_size_bytes: number;
  is_primary: boolean;
}

export interface DocumentWarning {
  filename: string;
  message: string;
}
