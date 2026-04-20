from __future__ import annotations

from app.modules.nlp.inference import NlpService
from app.modules.nlp.normalization import get_default_normalizer, load_normalization_audit_cases


def main() -> None:
    normalizer = get_default_normalizer()
    cases = load_normalization_audit_cases()

    print("\n=== Phase 9.8A normalization smoke evaluation ===\n")
    print(f"Normalizer enabled: {normalizer.enabled}")
    print(f"Dictionary version: {normalizer.dictionary_version}\n")

    try:
        service = NlpService.load_from_disk()
    except Exception as exc:
        service = None
        print(f"[WARN] Could not load NLP model: {exc}\n")

    for case in cases:
        text = case["text"]
        expected = case.get("expectedBehavior", "")

        result = normalizer.normalize(text)

        print("-" * 80)
        print(f"RAW:       {text}")
        print(f"CLEANED:   {result.cleaned_text}")
        print(f"CORRECTED: {result.corrected_text}")
        print(f"RULES:     {list(result.applied_rules)}")
        print(f"EXPECT:    {expected}")

        if service is not None:
            prediction = service.classify(text)
            top_labels = [
                f"{candidate.specialty_id}:{candidate.confidence:.4f}"
                for candidate in prediction.top_candidates
            ]
            print(f"TOP3:      {top_labels}")
            print(f"AMBIGUOUS: {prediction.needs_clarification}")
            print(f"REASON:    {prediction.reason_code}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()