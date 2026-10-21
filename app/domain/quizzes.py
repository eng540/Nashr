"""Typed quiz payloads for native Telegram quiz polls.

This module performs technical validation only; editorial quality remains a human decision.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class QuizPayload:
    question: str
    options: tuple[str, ...]
    correct_option_id: int
    explanation: str | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.question, str) or not self.question.strip():
            raise ValueError("Quiz question must not be empty.")
        if len(self.question) > 300:
            raise ValueError("Quiz question cannot exceed 300 characters.")
        if not isinstance(self.options, tuple) or not 2 <= len(self.options) <= 12:
            raise ValueError("Quiz must contain between 2 and 12 answer options.")
        for index, option in enumerate(self.options):
            if not isinstance(option, str) or not option.strip():
                raise ValueError(f"Quiz option {index + 1} must not be empty.")
            if len(option) > 100:
                raise ValueError(f"Quiz option {index + 1} cannot exceed 100 characters.")
        if isinstance(self.correct_option_id, bool) or not isinstance(self.correct_option_id, int):
            raise ValueError("Quiz correct_option_id must be an integer.")
        if not 0 <= self.correct_option_id < len(self.options):
            raise ValueError("Quiz correct_option_id must identify one of the supplied options.")
        if self.explanation is not None:
            if not isinstance(self.explanation, str):
                raise ValueError("Quiz explanation must be a string or null.")
            if len(self.explanation) > 200:
                raise ValueError("Quiz explanation cannot exceed 200 characters.")
            if self.explanation.count("\n") > 2:
                raise ValueError("Quiz explanation cannot contain more than two line feeds.")
        if self.source_reference is not None and not isinstance(self.source_reference, str):
            raise ValueError("Quiz source_reference must be a string or null.")

    @classmethod
    def from_dict(cls, value: object) -> "QuizPayload":
        """Parse persisted or model-generated JSON without coercing malformed option values."""
        if not isinstance(value, dict):
            raise ValueError("Quiz payload must be a JSON object.")
        options = value.get("options")
        if not isinstance(options, (list, tuple)):
            raise ValueError("Quiz options must be a JSON array.")
        return cls(
            question=value.get("question"),
            options=tuple(options),
            correct_option_id=value.get("correct_option_id"),
            explanation=value.get("explanation"),
            source_reference=value.get("source_reference"),
        )

    def to_telegram_payload(self, destination: str) -> dict[str, object]:
        """Build the Bot API sendPoll parameters for a native quiz."""
        payload: dict[str, object] = {
            "chat_id": destination,
            "question": self.question,
            "options": [{"text": option} for option in self.options],
            "type": "quiz",
            "correct_option_ids": [self.correct_option_id],
            "is_anonymous": True,
        }
        if self.explanation:
            payload["explanation"] = self.explanation
        return payload
