import pytest

from sakshi.intent import NOTES_MAX_KEYS, NOTES_MAX_LEN, NotesError, validate_notes


def test_notes_respect_razorpay_limits(intent):
    notes = intent.to_notes(gate_verdict="PASS")
    assert len(notes) <= NOTES_MAX_KEYS
    assert all(isinstance(v, str) and len(v) <= NOTES_MAX_LEN for v in notes.values())
    assert notes["sakshi_txn"] == "txn_test1"
    assert notes["sakshi_intent"] == intent.intent_hash()
    assert notes["sakshi_gate"] == "PASS"
    assert notes["sakshi_cap"] == "80000"


def test_raw_utterance_never_leaks(intent):
    notes = intent.to_notes()
    payload = intent.ledger_payload()
    assert "andar" not in " ".join(notes.values())
    assert intent.utterance not in str(payload)
    assert payload["utterance_hash"] == intent.utterance_hash()


def test_long_playback_is_truncated(intent):
    intent.playback = "x" * 1000
    notes = intent.to_notes()
    assert len(notes["sakshi_playback"]) == NOTES_MAX_LEN


def test_hash_changes_with_intent(intent):
    h = intent.intent_hash()
    intent.cap_paise = 90_000
    assert intent.intent_hash() != h


def test_validate_notes_rejects_bad_shapes():
    with pytest.raises(NotesError):
        validate_notes({f"k{i}": "v" for i in range(16)})
    with pytest.raises(NotesError):
        validate_notes({"k": "v" * 257})
    with pytest.raises(NotesError):
        validate_notes({"k": 5})
