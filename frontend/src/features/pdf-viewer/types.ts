import type { Citation } from "../analysis-detail/types";

export type { Citation };

export interface ViewerDocument {
  id: string;
  filename: string;
  is_primary: boolean;
  page_count?: number;
}
