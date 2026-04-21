import torch

from app.modules.nlp.inference import NlpService


class FakeTokenizer:
    def __call__(
        self,
        text: str,
        truncation: bool = True,
        padding: bool = True,
        max_length: int = 96,
        return_tensors: str = "pt",
    ):
        # The actual text content is irrelevant for threshold unit tests.
        # We just need something shaped like a tokenizer output.
        return {
            "input_ids": torch.tensor([[101, 2001, 102]], dtype=torch.long),
            "attention_mask": torch.tensor([[1, 1, 1]], dtype=torch.long),
        }


class FakeOutput:
    def __init__(self, logits: list[float]) -> None:
        self.logits = torch.tensor([logits], dtype=torch.float32)


class FakeModel:
    def __init__(self, logits: list[float]) -> None:
        self._logits = logits
        self.device = torch.device("cpu")

    def to(self, device: torch.device):
        self.device = device
        return self

    def eval(self):
        return self

    def __call__(self, **kwargs):
        return FakeOutput(self._logits)


def build_service(
    logits: list[float],
    *,
    min_confidence: float = 0.70,
    ambiguity_delta: float = 0.10,
) -> NlpService:
    label_to_id = {
        "cardiology": 0,
        "dermatology": 1,
        "neurology": 2,
    }
    id_to_label = {v: k for k, v in label_to_id.items()}

    return NlpService(
        tokenizer=FakeTokenizer(),
        model=FakeModel(logits),
        label_to_id=label_to_id,
        id_to_label=id_to_label,
        min_confidence=min_confidence,
        ambiguity_delta=ambiguity_delta,
        model_name="distilbert-specialty",
        model_version="1.0.0",
        device=torch.device("cpu"),
        max_length=96,
    )


def test_high_confidence_clear_winner() -> None:
    service = build_service([6.0, 1.0, -1.0])

    prediction = service.classify("chest pain when walking")

    assert prediction.reason_code == "OK"
    assert prediction.needs_clarification is False
    assert prediction.primary_specialty_id == "cardiology"
    assert prediction.top_candidates[0].specialty_id == "cardiology"
    assert prediction.top_candidates[0].confidence > 0.70
    assert prediction.clarifier_question is None


def test_low_confidence_is_ambiguous() -> None:
    service = build_service([1.0, 1.0, 1.0])

    prediction = service.classify("I do not feel well")

    assert prediction.reason_code == "NEEDS_CLARIFICATION"
    assert prediction.needs_clarification is True
    assert prediction.primary_specialty_id is None
    assert len(prediction.top_candidates) == 3
    assert prediction.clarifier_question is not None


def test_close_top_two_is_ambiguous_even_when_top_score_is_high_enough() -> None:
    # We lower min_confidence slightly so the ambiguity is caused mainly by the
    # small gap between the top two predictions.
    service = build_service(
        [5.0, 4.95, 0.10],
        min_confidence=0.50,
        ambiguity_delta=0.10,
    )

    prediction = service.classify("pain near my chest and shoulder")

    assert prediction.reason_code == "NEEDS_CLARIFICATION"
    assert prediction.needs_clarification is True
    assert prediction.primary_specialty_id is None
    assert prediction.top_candidates[0].specialty_id == "cardiology"
    assert prediction.top_candidates[1].specialty_id == "dermatology"


def test_candidate_ordering_is_deterministic_when_scores_tie() -> None:
    # Two equal top scores. The service sorts by:
    #   1) higher probability first
    #   2) lower label id first for ties
    service = build_service([3.0, 3.0, 1.0])

    prediction = service.classify("headache and skin problem")

    ordered_labels = [candidate.specialty_id for candidate in prediction.top_candidates]

    assert ordered_labels == ["cardiology", "dermatology", "neurology"]
    assert prediction.reason_code == "NEEDS_CLARIFICATION"
    
def build_custom_service(
    logits: list[float],
    *,
    label_to_id: dict[str, int],
    min_confidence: float = 0.70,
    ambiguity_delta: float = 0.10,
) -> NlpService:
    id_to_label = {v: k for k, v in label_to_id.items()}

    return NlpService(
        tokenizer=FakeTokenizer(),
        model=FakeModel(logits),
        label_to_id=label_to_id,
        id_to_label=id_to_label,
        min_confidence=min_confidence,
        ambiguity_delta=ambiguity_delta,
        model_name="distilbert-specialty",
        model_version="1.0.0",
        device=torch.device("cpu"),
        max_length=96,
    )


def test_ambiguous_prediction_includes_single_prompt_for_text_reply() -> None:
    service = build_service([1.0, 1.0, 1.0])

    prediction = service.classify("I do not feel well")

    assert prediction.reason_code == "NEEDS_CLARIFICATION"
    assert prediction.needs_clarification is True
    assert prediction.clarification_key == "free-text-clarification-only"
    assert prediction.clarifier_question is not None
    assert len(prediction.clarification_quick_replies) == 1
    assert prediction.clarification_quick_replies[0].label == "I will give more details"
    assert prediction.clarification_quick_replies[0].action == "PROMPT_FOR_TEXT"


def test_pair_specific_template_is_not_used_in_simplified_mode() -> None:
    service = build_custom_service(
        [5.0, 4.95, 0.10],
        label_to_id={
            "dermatology": 0,
            "ophthalmology": 1,
            "general_practice": 2,
        },
        min_confidence=0.50,
        ambiguity_delta=0.10,
    )

    prediction = service.classify("my eyelid skin is itchy and the eye feels irritated")

    assert prediction.needs_clarification is True
    assert prediction.clarification_key == "free-text-clarification-only"
    assert len(prediction.clarification_quick_replies) == 1
    assert prediction.clarification_quick_replies[0].label == "I will give more details"
    assert prediction.clarification_quick_replies[0].action == "PROMPT_FOR_TEXT"
    
def test_prediction_includes_preprocessing_trace_metadata() -> None:
    service = build_service([6.0, 1.0, -1.0])

    prediction = service.classify("Chest   pain!!! when walking")

    assert prediction.original_input_summary != ""
    assert prediction.cleaned_input_summary != ""
    assert prediction.normalized_input_summary != ""
    assert isinstance(prediction.preprocessing_actions, tuple)
    assert prediction.input_summary == prediction.normalized_input_summary