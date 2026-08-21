from typing import Protocol


class EmbeddingsPort(Protocol):
    def generate_embeddings(self, inputs: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
