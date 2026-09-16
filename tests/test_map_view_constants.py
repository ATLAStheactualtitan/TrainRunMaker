from foxhole_train_run_app import BASE_CIRCLE_RADIUS, build_phrases_for_selected_bases


def test_base_circle_radius_is_smaller_than_current_default():
    assert BASE_CIRCLE_RADIUS <= 2.0


def test_phrase_builder_labels_first_logi_and_remaining_region_messages():
    bases = [
        {"name": "Alpha", "region": "Region One"},
        {"name": "Bravo", "region": "Region Two"},
        {"name": "Charlie", "region": "Region Three"},
    ]

    phrases = build_phrases_for_selected_bases(bases)
    assert "LOGI CHAT MESSAGE" in phrases
    assert "REGION CHAT MESSAGES" in phrases
