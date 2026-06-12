from common.corpus import REQUIRED_METADATA_FIELDS, load_metadata


def test_metadata_schema_has_required_fields():
    docs = load_metadata()

    assert {doc["source_id"] for doc in docs} >= {
        "vendornova_profile",
        "vendornova_security_questionnaire",
        "procurement_policy",
        "infosec_vendor_policy",
        "contract_review_checklist",
        "public_seed_vendornova_001",
        "public_seed_vendornova_002",
        "executive_acquisition_memo",
        "injected_vendor_note",
    }
    for doc in docs:
        assert REQUIRED_METADATA_FIELDS.issubset(doc)
        assert doc["vendor_id"] == "vendornova"
        assert doc["storage_uri"].startswith("local://")
        assert len(doc["content_sha256"]) == 64
