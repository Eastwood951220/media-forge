from datetime import date

from scraper.profiles.actress import (
    ActorMetadata,
    ActressProfileMatch,
    ActressProfilePayload,
    dedupe_text,
)


def test_dedupe_text_preserves_order_and_drops_empty_values() -> None:
    assert dedupe_text(["七瀬アリス", "", None, "七瀬アリス", "七瀬愛麗絲"]) == [
        "七瀬アリス",
        "七瀬愛麗絲",
    ]


def test_actress_payload_dataclass_keeps_current_profile_fields() -> None:
    payload = ActressProfilePayload(
        display_name="宮上唯依花",
        reading="みやうえゆいか",
        source_url="https://db.avjoho.com/example/",
        aliases=["Miyaue Yuika"],
        debut_date=date(2020, 1, 2),
        birth_date=date(1998, 3, 4),
        height_cm=163,
        bust_cm=90,
        waist_cm=59,
        hip_cm=88,
        cup="E",
        sns_links=[{"label": "X", "url": "https://x.example"}],
    )

    assert payload.display_name == "宮上唯依花"
    assert payload.aliases == ["Miyaue Yuika"]
    assert payload.sns_links == [{"label": "X", "url": "https://x.example"}]


def test_actress_match_defaults_to_no_profile() -> None:
    match = ActressProfileMatch(
        profile=None,
        attempted_urls=["https://db.avjoho.com/missing/"],
        candidate_names=["missing"],
    )

    assert match.profile is None
    assert match.matched_url == ""
