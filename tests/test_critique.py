"""The style gate and the unattended critique-and-revise loop."""

from __future__ import annotations

from spine.critique.client import parse_notes
from spine.critique.loop import refine
from spine.critique.model import CLEAN, NO_PROGRESS, ROUNDS_EXHAUSTED
from spine.style.rules import StyleNote, hedges, long_sentences, puffery, review, shouting

CLEAN_TEXT = "The gate denies unknown viewers. Denials return 404 so ids stay hidden."


def test_clean_prose_gets_no_notes() -> None:
    assert review(text=CLEAN_TEXT) == ()


def test_a_long_sentence_is_flagged() -> None:
    sentence = "The system " + "and again ".join("word" for _ in range(40)) + " ends here."
    found = long_sentences(text=sentence)
    assert found[0].code == "long_sentence"


def test_hedges_are_flagged_by_word_not_substring() -> None:
    assert hedges(text="This is just wrong.")[0].excerpt == "just"
    assert hedges(text="Adjusted the justification.") == ()


def test_puffery_is_flagged() -> None:
    assert puffery(text="A robust and comprehensive design.")[0].code == "puffery"


def test_shouting_is_reported_once_with_a_count() -> None:
    found = shouting(text="This MUST hold. It is CRITICAL. You MUST comply.")
    assert len(found) == 1
    assert "3 shouted" in found[0].detail


def test_code_blocks_are_not_style_checked() -> None:
    assert review(text="```\nx = 1  # just a value, very robust\n```") == ()


def test_inline_code_is_not_style_checked() -> None:
    assert review(text="Call `simply_utilize()` here.") == ()


def test_urls_do_not_trip_the_gate() -> None:
    assert review(text="See https://example.com/really/very/simply/robust for context.") == ()


def _table(*, rows: int) -> str:
    header = "| Fact | Status |\n|---|---|\n"
    return header + "".join(
        f"| a robust unpunctuated cell number {each} | done |\n" for each in range(rows)
    )


def test_a_table_is_not_read_as_one_enormous_sentence() -> None:
    assert long_sentences(text=_table(rows=20)) == ()


def test_a_table_cell_does_not_trip_the_wording_rules() -> None:
    assert review(text=_table(rows=3)) == ()


def test_each_list_item_is_measured_on_its_own() -> None:
    listing = "\n".join(f"- item {each} has a few words in it" for each in range(30))
    assert long_sentences(text=listing) == ()


def test_a_single_overlong_list_item_is_still_caught() -> None:
    item = "- " + " ".join("word" for _ in range(50))
    assert long_sentences(text=item)[0].code == "long_sentence"


def test_headings_and_quotes_are_skipped() -> None:
    assert review(text="# A very robust heading\n\n> quoted text is simply not ours\n") == ()


def test_a_paragraph_split_across_lines_is_one_sentence() -> None:
    wrapped = "The gate denies\nunknown viewers and " + " ".join("word" for _ in range(40)) + "."
    assert len(long_sentences(text=wrapped)) == 1


class _FakeReviser:
    """Reports the notes it was seeded with, then hands back canned revisions."""

    def __init__(self, *, notes_per_round: tuple[tuple[StyleNote, ...], ...], revisions) -> None:
        self._notes_per_round = notes_per_round
        self._revisions = revisions
        self.critique_calls = 0
        self.revise_calls = 0

    def critique(self, *, text: str) -> tuple[StyleNote, ...]:
        index = min(self.critique_calls, len(self._notes_per_round) - 1)
        self.critique_calls += 1
        return self._notes_per_round[index]

    def revise(self, *, text: str, notes: tuple[StyleNote, ...]) -> str:
        index = min(self.revise_calls, len(self._revisions) - 1)
        self.revise_calls += 1
        return self._revisions[index]


def _note(*, code: str = "review:unsupported") -> StyleNote:
    return StyleNote(code=code, detail="a claim with nothing behind it")


def test_a_document_with_nothing_wrong_stops_clean_without_revising() -> None:
    reviser = _FakeReviser(notes_per_round=((),), revisions=("never used",))
    result = refine(text=CLEAN_TEXT, reviser=reviser)
    assert result.stop_reason == CLEAN
    assert result.text == CLEAN_TEXT
    assert reviser.revise_calls == 0


def test_the_loop_stops_as_soon_as_the_critique_comes_back_empty() -> None:
    reviser = _FakeReviser(notes_per_round=((_note(),), ()), revisions=(CLEAN_TEXT,))
    result = refine(text="It is basically fine.", reviser=reviser)
    assert result.stop_reason == CLEAN
    assert result.text == CLEAN_TEXT
    assert len(result.rounds) == 1


def test_the_loop_gives_up_after_the_round_limit() -> None:
    reviser = _FakeReviser(
        notes_per_round=((_note(),),), revisions=("one.", "two.", "three.", "four.")
    )
    result = refine(text="start.", reviser=reviser, max_rounds=2)
    assert result.stop_reason == ROUNDS_EXHAUSTED
    assert len(result.rounds) == 2
    assert result.remaining


def test_a_reviser_that_changes_nothing_stops_the_loop() -> None:
    reviser = _FakeReviser(notes_per_round=((_note(),),), revisions=("same.",))
    result = refine(text="same.", reviser=reviser, max_rounds=5)
    assert result.stop_reason == NO_PROGRESS
    assert reviser.revise_calls == 1


def test_mechanical_notes_reach_the_reviser_without_a_model() -> None:
    result = refine(text="This is basically fine.", reviser=None)
    assert result.stop_reason == ROUNDS_EXHAUSTED
    assert result.remaining[0].code == "hedge"
    assert result.text == "This is basically fine."


def test_the_style_gate_runs_before_the_model_each_round() -> None:
    reviser = _FakeReviser(notes_per_round=((),), revisions=(CLEAN_TEXT,))
    result = refine(text="This is basically fine.", reviser=reviser)
    assert result.rounds[0].notes[0].code == "hedge"
    assert result.stop_reason == CLEAN


def test_a_refinement_summarises_its_rounds() -> None:
    reviser = _FakeReviser(notes_per_round=((_note(),), ()), revisions=(CLEAN_TEXT,))
    lines = refine(text="This is basically fine.", reviser=reviser).summary_lines()
    assert lines[0].startswith("round 1:")
    assert any(line.startswith("stopped: clean") for line in lines)


def test_model_notes_parse_and_carry_a_prefix() -> None:
    payload = '{"notes": [{"code": "unsupported", "detail": "no evidence", "excerpt": "x"}]}'
    assert parse_notes(payload=payload)[0].code == "review:unsupported"


def test_a_malformed_note_is_dropped_rather_than_raising() -> None:
    payload = '{"notes": [{"code": "ok", "detail": "d", "excerpt": ""}, {"code": "no detail"}]}'
    assert len(parse_notes(payload=payload)) == 1


def test_an_empty_critique_parses_to_nothing() -> None:
    assert parse_notes(payload='{"notes": []}') == ()


def test_cli_exposes_the_critique_subcommand() -> None:
    from spine.cli import build_parser

    parsed = build_parser().parse_args(["critique", "check", "--file", "x.md"])
    assert parsed.handler is not None


def test_a_revision_that_balloons_is_flagged() -> None:
    reviser = _FakeReviser(notes_per_round=((_note(),), ()), revisions=("x" * 500,))
    result = refine(text="short draft.", reviser=reviser)
    assert result.has_grown_suspiciously
    assert "invented claims" in result.summary_lines()[-1]


def test_a_revision_that_stays_the_same_size_is_not_flagged() -> None:
    reviser = _FakeReviser(notes_per_round=((_note(),), ()), revisions=(CLEAN_TEXT,))
    result = refine(text="This is basically fine and about as long as that.", reviser=reviser)
    assert not result.has_grown_suspiciously


def test_a_refinement_with_no_rounds_is_never_flagged() -> None:
    assert not refine(text=CLEAN_TEXT, reviser=None).has_grown_suspiciously
