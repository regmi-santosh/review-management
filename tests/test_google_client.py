from app.google_client import MockGoogleBusinessProfileClient


def test_mock_fetch_reviews_matches_seed():
    client = MockGoogleBusinessProfileClient()
    reviews = client.fetch_reviews()
    assert len(reviews) == 6
    assert all(r.external_id.startswith("mock-") for r in reviews)
    assert all(1 <= r.rating <= 5 for r in reviews)
