from datetime import datetime
from typing import List, Tuple
from app import db
from app.models import Feed, Article
from app.services.rss_parser import RSSParser


class FeedFetcher:
    """Service for fetching and storing RSS feed articles."""

    @staticmethod
    def fetch_feed(feed: Feed) -> Tuple[int, int]:
        """
        Fetch articles from a single feed.

        Returns tuple of (new_count, updated_count).
        """
        new_count = 0
        updated_count = 0

        try:
            parsed = RSSParser.parse(feed.url)

            for entry_data in parsed['entries']:
                existing = Article.query.filter_by(guid=entry_data['guid']).first()

                if existing:
                    # Update if content changed
                    if existing.title != entry_data['title']:
                        existing.title = entry_data['title']
                        existing.description = entry_data['description']
                        existing.content = entry_data['content']
                        updated_count += 1
                else:
                    # Create new article
                    article = Article(
                        feed_id=feed.id,
                        guid=entry_data['guid'],
                        title=entry_data['title'],
                        link=entry_data['link'],
                        description=entry_data['description'],
                        content=entry_data['content'],
                        author=entry_data['author'],
                        thumbnail=entry_data.get('thumbnail', ''),
                        published_at=entry_data['published_at'],
                    )
                    db.session.add(article)
                    new_count += 1

            feed.last_fetched = datetime.utcnow()
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            raise e

        return new_count, updated_count

    @staticmethod
    def fetch_all_active() -> dict:
        """
        Fetch articles from all active feeds.

        Returns summary dict with results per feed.
        """
        results = {
            'total_new': 0,
            'total_updated': 0,
            'feeds': [],
            'errors': []
        }

        feeds = Feed.query.filter_by(is_active=True).all()

        for feed in feeds:
            try:
                new_count, updated_count = FeedFetcher.fetch_feed(feed)
                results['feeds'].append({
                    'id': feed.id,
                    'name': feed.name,
                    'new': new_count,
                    'updated': updated_count
                })
                results['total_new'] += new_count
                results['total_updated'] += updated_count
            except Exception as e:
                results['errors'].append({
                    'feed_id': feed.id,
                    'feed_name': feed.name,
                    'error': str(e)
                })

        return results
