import pytest

from app.domain.quizzes import QuizPayload


def test_quiz_payload_builds_native_telegram_quiz_poll():
    quiz = QuizPayload(
        question="ما جمع كلمة «قلم»؟",
        options=("أقلام", "قلمات", "قلام"),
        correct_option_id=0,
        explanation="جمع تكسير.",
    )
    payload = quiz.to_telegram_payload("@literature")
    assert payload == {
        "chat_id": "@literature",
        "question": "ما جمع كلمة «قلم»؟",
        "options": [{"text": "أقلام"}, {"text": "قلمات"}, {"text": "قلام"}],
        "type": "quiz",
        "correct_option_ids": [0],
        "is_anonymous": True,
        "explanation": "جمع تكسير.",
    }


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"question": "", "options": ("أ", "ب"), "correct_option_id": 0}, "question"),
        ({"question": "سؤال", "options": ("أ",), "correct_option_id": 0}, "between 2 and 12"),
        ({"question": "سؤال", "options": ("أ", "ب"), "correct_option_id": 2}, "identify"),
        ({"question": "سؤال", "options": ("أ" * 101, "ب"), "correct_option_id": 0}, "100 characters"),
        ({"question": "سؤال", "options": ("أ", "ب"), "correct_option_id": True}, "integer"),
        ({"question": "سؤال", "options": ("أ", "ب"), "correct_option_id": 0, "explanation": "س" * 201}, "200 characters"),
    ],
)
def test_quiz_payload_rejects_invalid_data(kwargs, message):
    with pytest.raises(ValueError, match=message):
        QuizPayload(**kwargs)
