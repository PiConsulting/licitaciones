from __future__ import annotations


def calculate_confidence_avg(extracted_data: dict | None) -> float | None:
    if not isinstance(extracted_data, dict):
        return None

    confidences: list[float] = []
    for value in extracted_data.values():
        if not isinstance(value, dict):
            continue

        extraction_status = value.get("extraction_status")
        confidence = value.get("confidence")

        if extraction_status != "success":
            continue

        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            continue

        confidences.append(float(confidence))

    if not confidences:
        return None

    return round(sum(confidences) / len(confidences), 3)
