import pytest
from app import create_app, db
from app.models import Feed, Article
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
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def sample_feed(app):
    """Create a sample feed."""
    with app.app_context():
        feed = Feed(
            name='Test Feed',
            url='https://example.com/rss',
            description='A test feed',
            category='tech',
            is_active=True
        )
        db.session.add(feed)
        db.session.commit()
        return feed.id


@pytest.fixture
def sample_article(app, sample_feed):
    """Create a sample article."""
    with app.app_context():
        article = Article(
            feed_id=sample_feed,
            guid='test-guid-123',
            title='Test Article',
            link='https://example.com/article',
            description='Test description',
            content='Full test content',
            author='Test Author',
            published_at=datetime.utcnow()
        )
        db.session.add(article)
        db.session.commit()
        return article.id


class TestHealthEndpoint:
    def test_health_check(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get('/api/v1/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'timestamp' in data


class TestFeedsAPI:
    def test_list_feeds_empty(self, client):
        """Test listing feeds when empty."""
        response = client.get('/feeds')
        assert response.status_code == 200
        data = response.get_json()
        assert data['feeds'] == []
        assert data['count'] == 0

    def test_list_feeds_with_data(self, client, sample_feed):
        """Test listing feeds with data."""
        response = client.get('/feeds')
        assert response.status_code == 200
        data = response.get_json()
        assert data['count'] == 1
        assert data['feeds'][0]['name'] == 'Test Feed'

    def test_get_feed(self, client, sample_feed):
        """Test getting a specific feed."""
        response = client.get(f'/feeds/{sample_feed}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['feed']['name'] == 'Test Feed'
        assert data['feed']['category'] == 'tech'

    def test_get_feed_not_found(self, client):
        """Test getting non-existent feed."""
        response = client.get('/feeds/999')
        assert response.status_code == 404

    def test_update_feed(self, client, sample_feed):
        """Test updating a feed."""
        response = client.put(
            f'/feeds/{sample_feed}',
            json={'name': 'Updated Feed', 'category': 'news'}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data['feed']['name'] == 'Updated Feed'
        assert data['feed']['category'] == 'news'

    def test_delete_feed(self, client, sample_feed):
        """Test deleting a feed."""
        response = client.delete(f'/feeds/{sample_feed}')
        assert response.status_code == 200

        # Verify it's gone
        response = client.get(f'/feeds/{sample_feed}')
        assert response.status_code == 404


class TestArticlesAPI:
    def test_list_articles_empty(self, client):
        """Test listing articles when empty."""
        response = client.get('/articles')
        assert response.status_code == 200
        data = response.get_json()
        assert data['articles'] == []

    def test_list_articles_with_data(self, client, sample_article):
        """Test listing articles with data."""
        response = client.get('/articles')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['articles']) == 1
        assert data['articles'][0]['title'] == 'Test Article'

    def test_get_article(self, client, sample_article):
        """Test getting a specific article."""
        response = client.get(f'/articles/{sample_article}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['article']['title'] == 'Test Article'
        assert data['article']['content'] == 'Full test content'

    def test_latest_articles(self, client, sample_article):
        """Test getting latest articles."""
        response = client.get('/articles/latest')
        assert response.status_code == 200
        data = response.get_json()
        assert data['count'] == 1

    def test_mark_read(self, client, sample_article):
        """Test marking article as read."""
        response = client.post(f'/articles/{sample_article}/read')
        assert response.status_code == 200
        data = response.get_json()
        assert data['article']['is_read'] is True

    def test_mark_unread(self, client, sample_article):
        """Test marking article as unread."""
        # First mark as read
        client.post(f'/articles/{sample_article}/read')
        # Then mark as unread
        response = client.post(f'/articles/{sample_article}/unread')
        assert response.status_code == 200
        data = response.get_json()
        assert data['article']['is_read'] is False

    def test_star_article(self, client, sample_article):
        """Test starring an article."""
        response = client.post(f'/articles/{sample_article}/star')
        assert response.status_code == 200
        data = response.get_json()
        assert data['article']['is_starred'] is True

    def test_filter_by_feed(self, client, sample_feed, sample_article):
        """Test filtering articles by feed."""
        response = client.get(f'/articles?feed_id={sample_feed}')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['articles']) == 1

    def test_filter_by_category(self, client, sample_article):
        """Test filtering articles by category."""
        response = client.get('/articles?category=tech')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['articles']) == 1

    def test_search_articles(self, client, sample_article):
        """Test searching articles."""
        response = client.get('/articles?search=Test')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['articles']) == 1


class TestNewsAPI:
    def test_get_news(self, client, sample_article):
        """Test dynamic news endpoint."""
        response = client.get('/api/v1/news')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['news']) == 1
        assert 'meta' in data

    def test_get_news_with_limit(self, client, sample_article):
        """Test news endpoint with limit."""
        response = client.get('/api/v1/news?limit=10')
        assert response.status_code == 200
        data = response.get_json()
        assert data['meta']['limit'] == 10

    def test_get_news_stream(self, client, sample_article):
        """Test news stream endpoint."""
        response = client.get('/api/v1/news/stream')
        assert response.status_code == 200
        data = response.get_json()
        assert 'items' in data
        assert 'poll_after' in data


class TestStatsAPI:
    def test_get_stats(self, client, sample_feed, sample_article):
        """Test stats endpoint."""
        response = client.get('/api/v1/stats')
        assert response.status_code == 200
        data = response.get_json()
        assert data['feeds']['total'] == 1
        assert data['articles']['total'] == 1

    def test_get_categories(self, client, sample_feed, sample_article):
        """Test categories endpoint."""
        response = client.get('/api/v1/categories')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['categories']) == 1
        assert data['categories'][0]['name'] == 'tech'
