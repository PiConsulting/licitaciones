import type { HighlightCoordinates } from "./types";

interface PDFHighlighterProps {
  coordinates: HighlightCoordinates[];
}

export function PDFHighlighter({ coordinates }: PDFHighlighterProps) {
  if (coordinates.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none absolute inset-0" data-testid="highlight-overlay">
      {coordinates.map((coordinate, index) => (
        <div
          // eslint-disable-next-line react/no-array-index-key
          key={index}
          className="absolute"
          style={{
            left: coordinate.x,
            top: coordinate.y,
            width: coordinate.width,
            height: coordinate.height,
            backgroundColor: "#FEF3C7",
            opacity: 0.3,
          }}
        />
      ))}
    </div>
  );
}
