# backend/tests/test_contracts.py
from backtrace.contracts.complaints import ComplaintOut
from backtrace.contracts.evidence import EvidencePackStub
from backtrace.contracts.extraction import ComplaintExtraction


def test_complaint_extraction_requires_issues_field():
    extraction = ComplaintExtraction(
        product="fiber_basic",
        symptoms=["no internet"],
        claimed_cause="router broken",
        issues=["no internet"],
    )
    assert extraction.issues == ["no internet"]


def test_complaint_out_serializes_from_orm_style_object():
    import datetime as dt

    class FakeRow:
        complaint_id = "c1"
        customer_id = "cust1"
        received_at = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        channel = "web"
        text = "down"
        product = "fiber_basic"
        region = "north"

    dto = ComplaintOut.model_validate(FakeRow())
    assert dto.complaint_id == "c1"


def test_evidence_pack_stub_round_trips_json():
    pack = EvidencePackStub(cohort_id="coh1", complaint_ids=["c1"], event_ids=["e1"], anomaly_ids=[])
    assert EvidencePackStub.model_validate_json(pack.model_dump_json()) == pack
