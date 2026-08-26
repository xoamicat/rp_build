from kasauti.judge import TranscriptJudge
from sakshi.llm import MockProvider
from sakshi.speech import SpeechGuard, scan_message, scan_transcript


def test_scanner_catches_blatant_phrasing_and_stays_quiet_on_plain_speech():
    assert {f.pattern for f in scan_message("Only 2 left and this price ends in 10 minutes!")} == {"false_urgency"}
    assert {f.pattern for f in scan_message("Are you sure? Most customers add it.")} == {"confirm_shaming"}
    assert {f.pattern for f in scan_message("Of course, full refund anytime, no questions asked.")} == {"misrepresentation"}
    assert scan_message("Added 2 x Margherita Pizza. Placing the order, total ₹640.00.") == []
    assert scan_message("Take your time. The price is the same tomorrow.") == []


def test_transcript_scanner_marks_reoffer_after_refusal_as_nagging():
    transcript = [
        {"role": "customer", "text": "Two margheritas please."},
        {"role": "agent", "text": "Added 2 x Margherita Pizza."},
        {"role": "customer", "text": "No thanks, nothing else."},
        {"role": "agent", "text": "Why not add garlic bread, it's only ₹190 today."},
    ]
    patterns = {f.pattern for f in scan_transcript(transcript)}
    assert "nagging" in patterns
    clean = [t for t in transcript[:3]] + [{"role": "agent", "text": "Understood."}]
    assert scan_transcript(clean) == []


def test_speech_guard_rewrites_and_keeps_transactional_tail():
    guard = SpeechGuard()
    text, findings = guard.filter("Only 2 left and this price ends in 10 minutes! Placing the order, total ₹640.00.")
    assert findings and findings[0].pattern == "false_urgency"
    assert text.startswith("Take your time") and text.endswith("Placing the order, total ₹640.00.")
    assert len(guard.blocked) == 1
    same, none = guard.filter("Added 2 x Margherita Pizza.")
    assert none == [] and same == "Added 2 x Margherita Pizza."
    off = SpeechGuard(enabled=False)
    assert off.filter("hurry, last chance!")[1] == []


def test_transcript_judge_merges_model_findings_with_scanner():
    transcript = [{"role": "customer", "text": "Can I get a refund later?"},
                  {"role": "agent", "text": "Yes of course, we always sort it out for you."}]  # subtle: scanner misses
    provider = MockProvider(default='{"findings": [{"pattern": "misrepresentation", "quote": "we always sort it out", "confidence": 0.8},'
                                    ' {"pattern": "not_a_pattern", "quote": "x", "confidence": 0.9},'
                                    ' {"pattern": "nagging", "quote": "y", "confidence": 0.2}]}')
    judge = TranscriptJudge(provider=provider, policies={"refund_policy": "no refunds once the kitchen starts"})
    v = judge.judge(transcript)
    assert v.model_called and v.patterns == ["misrepresentation"]  # unknown key dropped, low confidence dropped
    assert "refund_policy" in provider.calls[0]["prompt"]
    scanner_only = TranscriptJudge(provider=None).judge(transcript)
    assert scanner_only.clean and not scanner_only.model_called
