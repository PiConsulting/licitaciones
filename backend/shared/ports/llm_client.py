from abc import ABC, abstractmethod


class LLMClientPort(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Generate completion text for a prompt."""
