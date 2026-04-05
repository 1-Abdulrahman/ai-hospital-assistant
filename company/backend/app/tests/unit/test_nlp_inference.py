import json
from pathlib import Path

import torch

from app.modules.nlp import inference


class DummyTokenizer:
    def __call__(self, *args, **kwargs):
        return {
            "input_ids": torch.tensor([[101, 102]], dtype=torch.long),
            "attention_mask": torch.tensor([[1, 1]], dtype=torch.long),
        }


class DummyModel:
    def __init__(self) -> None:
        self.device = torch.device("cpu")

    def to(self, device: torch.device):
        self.device = device
        return self

    def eval(self):
        return self

    def __call__(self, **kwargs):
        class Output:
            logits = torch.tensor([[3.0, 1.0, 0.5]], dtype=torch.float32)
        return Output()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_try_load_nlp_service_returns_fallback_when_model_dir_is_missing(tmp_path) -> None:
    missing_model_dir = tmp_path / "missing-model-dir"

    service, status = inference.try_load_nlp_service(
        model_dir=missing_model_dir,
        local_files_only=True,
    )

    assert service is None
    assert status["available"] is False
    assert status["reasonCode"] == "NLP_PROCESSING_FAILED"
    assert "Manual specialty selection" in status["message"]


def test_load_from_disk_uses_local_artifacts_only(tmp_path, monkeypatch) -> None:
    model_dir = tmp_path / "distilbert-specialty"
    model_dir.mkdir(parents=True, exist_ok=True)

    label_to_id_path = model_dir / "label_to_id.json"
    labels_path = model_dir / "labels.json"
    thresholds_path = model_dir / "thresholds.json"
    model_version_path = model_dir / "model_version.txt"

    write_json(
        label_to_id_path,
        {
            "cardiology": 0,
            "dermatology": 1,
            "neurology": 2,
        },
    )
    write_json(labels_path, ["cardiology", "dermatology", "neurology"])
    write_json(
        thresholds_path,
        {
            "minConfidence": 0.70,
            "ambiguityDelta": 0.10,
        },
    )
    model_version_path.write_text("1.0.0", encoding="utf-8")

    # The current inference.py reads these module-level paths directly,
    # so we patch them to point at our temp model folder.
    monkeypatch.setattr(inference, "LABEL_TO_ID_PATH", label_to_id_path)
    monkeypatch.setattr(inference, "LABELS_PATH", labels_path)
    monkeypatch.setattr(inference, "THRESHOLDS_PATH", thresholds_path)
    monkeypatch.setattr(inference, "MODEL_VERSION_PATH", model_version_path)

    # Force CPU in tests
    monkeypatch.setattr(inference.torch.cuda, "is_available", lambda: False)

    calls = {
        "tokenizer": None,
        "model": None,
    }

    class DummyAutoTokenizer:
        @classmethod
        def from_pretrained(cls, path: str, local_files_only: bool = False):
            calls["tokenizer"] = {
                "path": path,
                "local_files_only": local_files_only,
            }
            return DummyTokenizer()

    class DummyAutoModel:
        @classmethod
        def from_pretrained(cls, path: str, local_files_only: bool = False):
            calls["model"] = {
                "path": path,
                "local_files_only": local_files_only,
            }
            return DummyModel()

    monkeypatch.setattr(inference, "AutoTokenizer", DummyAutoTokenizer)
    monkeypatch.setattr(inference, "AutoModelForSequenceClassification", DummyAutoModel)

    service = inference.NlpService.load_from_disk(
        model_dir=model_dir,
        local_files_only=True,
    )

    assert service is not None
    assert service.model_name == "distilbert-specialty"
    assert service.model_version == "1.0.0"
    assert service.min_confidence == 0.70
    assert service.ambiguity_delta == 0.10
    assert service.status()["labelsCount"] == 3

    assert calls["tokenizer"]["path"] == str(model_dir)
    assert calls["model"]["path"] == str(model_dir)
    assert calls["tokenizer"]["local_files_only"] is True
    assert calls["model"]["local_files_only"] is True