from app.modules.nlp.training.split_utils import TrainingRow, split_rows_family_aware


def test_family_aware_split_keeps_groups_together() -> None:
    rows = [
        TrainingRow("cardio a1", "cardiology", "fam_cardio_1", "k1"),
        TrainingRow("cardio a2", "cardiology", "fam_cardio_1", "k2"),
        TrainingRow("cardio b1", "cardiology", "fam_cardio_2", "k3"),
        TrainingRow("cardio c1", "cardiology", "fam_cardio_3", "k4"),
        TrainingRow("derm a1", "dermatology", "fam_derm_1", "k5"),
        TrainingRow("derm a2", "dermatology", "fam_derm_1", "k6"),
        TrainingRow("derm b1", "dermatology", "fam_derm_2", "k7"),
        TrainingRow("derm c1", "dermatology", "fam_derm_3", "k8"),
        TrainingRow("gp a1", "general_practice", "fam_gp_1", "k9"),
        TrainingRow("gp a2", "general_practice", "fam_gp_1", "k10"),
        TrainingRow("gp b1", "general_practice", "fam_gp_2", "k11"),
        TrainingRow("gp c1", "general_practice", "fam_gp_3", "k12"),
    ]

    split_result = split_rows_family_aware(rows, seed=42)

    train_groups = set(split_result["train_group_keys"])
    val_groups = set(split_result["val_group_keys"])
    test_groups = set(split_result["test_group_keys"])

    assert train_groups.isdisjoint(val_groups)
    assert train_groups.isdisjoint(test_groups)
    assert val_groups.isdisjoint(test_groups)

    all_seen = train_groups | val_groups | test_groups
    assert all_seen == {
        "fam_cardio_1",
        "fam_cardio_2",
        "fam_cardio_3",
        "fam_derm_1",
        "fam_derm_2",
        "fam_derm_3",
        "fam_gp_1",
        "fam_gp_2",
        "fam_gp_3",
    }