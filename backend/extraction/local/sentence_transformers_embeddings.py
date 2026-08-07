from __future__ import annotations

from extraction.ports.embeddings_port import EmbeddingsPort


class LocalEmbeddingsAdapter(EmbeddingsPort):
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    def generate_embeddings(self, inputs: list[str]) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(self._model_name)
        vectors = model.encode(inputs, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]
