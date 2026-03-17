import pytest
from cnintendo.models import Article, ImageInfo, IssueData, IssueMetadata, PageProcessed, IssuePages


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


def test_page_processed_minimal():
    p = PageProcessed(page_number=1)
    assert p.image_path is None
    assert p.djvu_text is None
    assert p.llm is None


def test_page_processed_with_llm():
    p = PageProcessed(
        page_number=3,
        image_path="2005/08/images/page_0003.jpg",
        djvu_text="Mario Kart DS review...",
        page_type_scandata="Normal",
        llm={"page_type": "review", "game": "Mario Kart DS", "score": 9.0}
    )
    assert p.llm["game"] == "Mario Kart DS"
    assert p.page_type_scandata == "Normal"


def test_issue_pages_minimal():
    issue = IssuePages(
        ia_identifier="ClubTest",
        canonical_stem="club-nintendo_1991-01_a01-n01",
        filename="test.pdf",
        total_pages=0,
    )
    assert issue.pages == []
    assert issue.ia_subjects == []


def test_issue_pages_full():
    issue = IssuePages(
        ia_identifier="ClubNintendoMxicoAAo14N08",
        ia_title="Club Nintendo Año 14 N° 08 (México)",
        ia_date="2005-08",
        ia_description="Club Nintendo Año 14 N° 8 — Agosto de 2005",
        ia_clubnintendo="No1408",
        ia_subjects=["videojuegos", "nintendo"],
        canonical_stem="club-nintendo_2005-08_a14-n08",
        filename="Club Nintendo.pdf",
        total_pages=80,
        pages=[PageProcessed(page_number=1, llm={"summary": "Portada"})]
    )
    assert len(issue.pages) == 1
    assert issue.ia_clubnintendo == "No1408"
