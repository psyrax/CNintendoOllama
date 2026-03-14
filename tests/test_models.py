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
    data = IssueData(issue=meta, articles=[])
    json_str = data.model_dump_json()
    assert "issue" in json_str
    assert "articles" in json_str
