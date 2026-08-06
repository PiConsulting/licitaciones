import type { Citation } from "../analysis-detail/types";

export type { Citation };

export interface ViewerDocument {
  id: string;
  filename: string;
  is_primary: boolean;
  page_count?: number;
}

export interface HighlightCoordinates {
  x: number;
  y: number;
  width: number;
  height: number;
}
