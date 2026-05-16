# NLP Dataset Labeling Policy v1

## Primary rule
Assign exactly one `label` as the primary training target.

## Secondary labels
Use `secondary_labels` only for plausible confusion classes.

## General practice
Use `general_practice` when the complaint is vague, mixed, or lacks enough specialty-specific clues.

## Label intent
- cardiology: chest pain, exertional tightness, palpitations, shortness of breath with cardiac flavor
- dermatology: rash, itching, skin patches, redness, acne, eczema-like complaints
- orthopedics: joint pain, knee pain, back pain, injury, sprain, stiffness, movement limitation
- ent: sore throat, swallowing pain, sinus congestion, ear pain, hoarseness
- ophthalmology: blurry vision, eye pain, red eyes, light sensitivity, watering
- neurology: headache, dizziness, fainting, tingling, balance, seizure-like symptoms
- gastroenterology: stomach pain, abdominal pain, nausea, vomiting, reflux, bloating, bowel symptoms
- pediatrics: child-centered complaints where pediatric routing is appropriate
- general_practice: broad or low-specificity complaints such as fatigue, feverishness, body aches, general weakness

## Review rules
- No duplicate complaint text with different primary labels.
- If a complaint is borderline, keep one primary label and list the others in `secondary_labels`.
- Keep complaint text in short patient style, not long clinical notes.
- Do not include private identifiers or real PHI.