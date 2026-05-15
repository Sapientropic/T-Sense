from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mobile_sources_grid_keeps_source_recommendations_area():
    css = (ROOT / "dashboard" / "src" / "styles" / "responsive.css").read_text(encoding="utf-8")

    assert '"source-import"\n      "source-library"\n      "source-recommendations"' in css


def test_profile_matching_cards_do_not_stretch_bullets_into_blank_rows():
    css = (ROOT / "dashboard" / "src" / "styles" / "profiles.css").read_text(encoding="utf-8")

    assert ".profile-match-section,\n.profile-matching-more section {\n  display: grid;\n  align-content: start;" in css
    assert ".profile-match-section ul,\n.profile-matching-more ul {\n  display: grid;\n  align-content: start;" in css
