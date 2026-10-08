export function splitLabelAndValue(text: string): { label: string; value: string } | null {
  const separatorIndex = text.indexOf(":");
  if (separatorIndex <= 0) {
    return null;
  }
  const label = text.slice(0, separatorIndex).trim();
  const value = text.slice(separatorIndex + 1).trim();
  if (!label || !value) {
    return null;
  }
  return { label, value };
}
