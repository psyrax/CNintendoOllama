import pytest
from cnintendo.models import IssueMetadata, Article, IssueData

def test_issue_metadata_defaults():
    meta = IssueMetadata(filename="test.pdf", pages=10)
    assert meta.type == "unknown"
    assert meta.number is None

def test_issue_metadata_full():
    meta = IssueMetadata(
        id="test-001",
        filename="revista_001.pdf",
        number=1,
        year=1995,
        month="enero",
        pages=84,
        type="native"
    )
    assert meta.id == "test-001"
    assert meta.type == "native"

def test_article_defaults():
    article = Article(page=1, title="Test")
    assert article.section == "unknown"
    assert article.score is None
    assert article.images == []

def test_issue_data_serialization():
    meta = IssueMetadata(filename="test.pdf", pages=10)
    article = Article(page=1, title="Mario", game="Super Mario 64", score=97.0)
    data = IssueData(issue=meta, articles=[article])
    # Round-trip: serialize then deserialize
    restored = IssueData.model_validate_json(data.model_dump_json())
    assert restored.issue.filename == "test.pdf"
    assert len(restored.articles) == 1
    assert restored.articles[0].score == 97.0

def test_issue_metadata_invalid_type():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        IssueMetadata(filename="test.pdf", pages=1, type="invalid_type")
