import pytest
from cnintendo.models import Article, ImageInfo, IssueData, IssueMetadata


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


def test_issue_metadata_ia_fields():
    m = IssueMetadata(
        filename="test.pdf", pages=30,
        ia_title="Club Nintendo Año 01",
        ia_subjects=["videojuegos", "nintendo"],
        ia_date="1991-01",
        ia_identifier="ClubNintendoAo01N01Mxico",
    )
    assert m.ia_title == "Club Nintendo Año 01"
    assert m.ia_subjects == ["videojuegos", "nintendo"]


def test_issue_metadata_ia_fields_optional():
    m = IssueMetadata(filename="test.pdf", pages=30)
    assert m.ia_title is None
    assert m.ia_subjects == []


def test_image_info_model():
    img = ImageInfo(path="data/images/test.png")
    assert img.description is None
    img2 = ImageInfo(path="data/images/test.png", description="Mario saltando")
    assert img2.description == "Mario saltando"


def test_article_images_as_image_info():
    a = Article(page=1, images=[ImageInfo(path="img.png", description="desc")])
    assert a.images[0].path == "img.png"
    assert a.images[0].description == "desc"


def test_issue_data_summary():
    m = IssueMetadata(filename="test.pdf", pages=10)
    d = IssueData(issue=m, summary="Resumen del número.")
    assert d.summary == "Resumen del número."


def test_issue_data_summary_optional():
    m = IssueMetadata(filename="test.pdf", pages=10)
    d = IssueData(issue=m)
    assert d.summary is None


def test_article_images_coerces_strings():
    a = Article(page=1, images=["img.png", "img2.png"])
    assert len(a.images) == 2
    assert a.images[0].path == "img.png"
    assert a.images[0].description is None
