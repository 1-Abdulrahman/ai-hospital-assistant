from __future__ import annotations

from types import SimpleNamespace

import torch

from app.modules.nlp.inference import NlpService


class CapturingTokenizer:
    def __init__(self) -> None:
        self.last_text: str | None = None

    def __call__(
        self,
        text: str,
        truncation: bool = True,
        padding: bool = True,
        max_length: int = 96,
        return_tensors: str = "pt",
    ):
        self.last_text = text
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


class FakeNormalizer:
    def normalize(self, text: str):
        return SimpleNamespace(
            raw_text=text,
            cleaned_text="i feel nausia",
            corrected_text="i feel nausea",
            applied_rules=("basic_cleanup", "symspell_lookup_compound"),
        )


def test_classify_uses_normalized_text(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.nlp.inference.get_default_normalizer",
        lambda: FakeNormalizer(),
    )

    tokenizer = CapturingTokenizer()

    service = NlpService(
        tokenizer=tokenizer,
        model=FakeModel([6.0, 1.0, -1.0]),
        label_to_id={
            "cardiology": 0,
            "dermatology": 1,
            "neurology": 2,
        },
        id_to_label={
            0: "cardiology",
            1: "dermatology",
            2: "neurology",
        },
        min_confidence=0.70,
        ambiguity_delta=0.10,
        model_name="distilbert-specialty",
        model_version="1.0.0",
        device=torch.device("cpu"),
        max_length=96,
    )

    service.classify("I FEEL NAUSIA!!!")

    assert tokenizer.last_text == "i feel nausea"