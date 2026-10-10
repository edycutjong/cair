"""Line + branch coverage for cair/tracing.py: trace-id extraction from the neatlogs carrier. No network."""
import pytest

from cair import tracing

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SPAN_ID = "b7ad6b7169203331"


def _fake_inject(monkeypatch, carrier_update, result=True):
    seen = []

    def inject(carrier):
        seen.append(carrier)
        carrier.update(carrier_update)
        return result

    monkeypatch.setattr(tracing.neatlogs, "inject_trace_context", inject, raising=False)
    return seen


def test_returns_trace_id_from_traceparent(monkeypatch):
    seen = _fake_inject(monkeypatch, {"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"})
    assert tracing.current_trace_id() == TRACE_ID
    assert len(seen) == 1  # the carrier handed to neatlogs is the one that was parsed


def test_no_active_span_returns_none(monkeypatch):
    # inject reports failure: any stale carrier content must be ignored
    _fake_inject(monkeypatch, {"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01"}, result=False)
    assert tracing.current_trace_id() is None


@pytest.mark.parametrize("carrier", [
    {},                                             # header absent
    {"traceparent": ""},                            # empty header
    {"traceparent": f"00-{TRACE_ID}-{SPAN_ID}"},    # too few fields
    {"traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01-xx"},  # too many fields
])
def test_malformed_traceparent_returns_none(monkeypatch, carrier):
    _fake_inject(monkeypatch, carrier)
    assert tracing.current_trace_id() is None
