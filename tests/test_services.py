import pytest
from unittest.mock import patch, MagicMock
from app import create_app, db
from app.models import Feed, Article
from app.services import RSSParser, FeedFetcher
from datetime import datetime


@pytest.fixture
def app():
    """Create test application."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def sample_feed(app):
    """Create a sample feed for testing."""
    with app.app_context():
        feed = Feed(
            name='Test Feed',
            url='https://example.com/rss',
            is_active=True
        )
        db.session.add(feed)
        db.session.commit()
        feed_id = feed.id
    return feed_id


class TestRSSParser:
    @patch('app.services.rss_parser.feedparser.parse')
    def test_parse_valid_feed(self, mock_parse):
        """Test parsing a valid RSS feed."""
        mock_parse.return_value = MagicMock(
            bozo=False,
            feed={'title': 'Test Feed', 'description': 'A test', 'link': 'https://example.com', 'language': 'en'},
            entries=[
                MagicMock(
                    get=lambda k, d='': {'id': 'guid1', 'title': 'Article 1', 'link': 'https://example.com/1', 'summary': 'Summary 1', 'author': 'Author'}.get(k, d),
                    published_parsed=None,
                    updated_parsed=None,
                    content=None,
                    summary='Summary 1'
                )
            ]
        )
        # Mock entry properly
        mock_parse.return_value.entries[0].__contains__ = lambda self, k: k in ['id', 'title', 'link', 'summary', 'author']

        result = RSSParser.parse('https://example.com/rss')

        assert result['feed']['title'] == 'Test Feed'
        assert len(result['entries']) == 1

    @patch('app.services.rss_parser.feedparser.parse')
    def test_parse_invalid_feed(self, mock_parse):
        """Test parsing an invalid feed raises error."""
        mock_parse.return_value = MagicMock(
            bozo=True,
            bozo_exception=Exception('Parse error'),
            entries=[]
        )

        with pytest.raises(ValueError, match='Failed to parse feed'):
            RSSParser.parse('https://invalid.com/rss')


class TestFeedFetcher:
    @patch('app.services.feed_fetcher.RSSParser.parse')
    def test_fetch_feed_new_articles(self, mock_parse, app, sample_feed):
        """Test fetching new articles."""
        mock_parse.return_value = {
            'feed': {'title': 'Test'},
            'entries': [
                {
                    'guid': 'new-guid-1',
                    'title': 'New Article',
                    'link': 'https://example.com/new',
                    'description': 'New desc',
                    'content': 'Content',
                    'author': 'Author',
                    'published_at': datetime.utcnow()
                }
            ]
        }

        with app.app_context():
            feed = db.session.get(Feed, sample_feed)
            new_count, updated_count = FeedFetcher.fetch_feed(feed)

            assert new_count == 1
            assert updated_count == 0

            # Verify article was created
            article = Article.query.filter_by(guid='new-guid-1').first()
            assert article is not None
            assert article.title == 'New Article'

    @patch('app.services.feed_fetcher.RSSParser.parse')
    def test_fetch_feed_duplicate_articles(self, mock_parse, app, sample_feed):
        """Test that duplicate articles are not created."""
        entry_data = {
            'guid': 'duplicate-guid',
            'title': 'Article',
            'link': 'https://example.com/dup',
            'description': 'Desc',
            'content': 'Content',
            'author': 'Author',
            'published_at': datetime.utcnow()
        }
        mock_parse.return_value = {
            'feed': {'title': 'Test'},
            'entries': [entry_data]
        }

        with app.app_context():
            feed = db.session.get(Feed, sample_feed)

            # First fetch
            new1, _ = FeedFetcher.fetch_feed(feed)
            assert new1 == 1

            # Second fetch - same article
            new2, _ = FeedFetcher.fetch_feed(feed)
            assert new2 == 0

            # Only one article should exist
            count = Article.query.filter_by(guid='duplicate-guid').count()
            assert count == 1

    @patch('app.services.feed_fetcher.RSSParser.parse')
    def test_fetch_all_active(self, mock_parse, app, sample_feed):
        """Test fetching all active feeds."""
        mock_parse.return_value = {
            'feed': {'title': 'Test'},
            'entries': [
                {
                    'guid': 'batch-guid',
                    'title': 'Batch Article',
                    'link': 'https://example.com/batch',
                    'description': 'Desc',
                    'content': 'Content',
                    'author': 'Author',
                    'published_at': datetime.utcnow()
                }
            ]
        }

        with app.app_context():
            results = FeedFetcher.fetch_all_active()

            assert results['total_new'] == 1
            assert len(results['feeds']) == 1
            assert len(results['errors']) == 0
