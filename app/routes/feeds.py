from flask import Blueprint, request, jsonify
from app import db
from app.models import Feed
from app.services import FeedFetcher, RSSParser

feeds_bp = Blueprint('feeds', __name__)


@feeds_bp.route('', methods=['GET'])
def list_feeds():
    """List all RSS feeds."""
    feeds = Feed.query.order_by(Feed.created_at.desc()).all()
    return jsonify({
        'feeds': [f.to_dict() for f in feeds],
        'count': len(feeds)
    })


@feeds_bp.route('', methods=['POST'])
def create_feed():
    """Add a new RSS feed."""
    data = request.get_json()

    if not data or not data.get('url'):
        return jsonify({'error': 'URL is required'}), 400

    url = data['url']

    # Check if feed already exists
    existing = Feed.query.filter_by(url=url).first()
    if existing:
        return jsonify({'error': 'Feed already exists', 'feed': existing.to_dict()}), 409

    # Parse feed to get metadata
    try:
        parsed = RSSParser.parse(url)
        feed_info = parsed['feed']
    except Exception as e:
        return jsonify({'error': f'Failed to parse feed: {str(e)}'}), 400

    # Create feed
    feed = Feed(
        name=data.get('name') or feed_info['title'],
        url=url,
        description=data.get('description') or feed_info['description'],
        category=data.get('category'),
        is_active=data.get('is_active', True)
    )

    db.session.add(feed)
    db.session.commit()

    # Optionally fetch articles immediately
    if data.get('fetch_now', True):
        try:
            new_count, _ = FeedFetcher.fetch_feed(feed)
            return jsonify({
                'message': 'Feed created and fetched',
                'feed': feed.to_dict(),
                'articles_fetched': new_count
            }), 201
        except Exception as e:
            return jsonify({
                'message': 'Feed created but fetch failed',
                'feed': feed.to_dict(),
                'fetch_error': str(e)
            }), 201

    return jsonify({'message': 'Feed created', 'feed': feed.to_dict()}), 201


@feeds_bp.route('/<int:feed_id>', methods=['GET'])
def get_feed(feed_id):
    """Get a specific feed."""
    feed = Feed.query.get_or_404(feed_id)
    return jsonify({'feed': feed.to_dict()})


@feeds_bp.route('/<int:feed_id>', methods=['PUT'])
def update_feed(feed_id):
    """Update a feed."""
    feed = Feed.query.get_or_404(feed_id)
    data = request.get_json()

    if data.get('name'):
        feed.name = data['name']
    if data.get('description') is not None:
        feed.description = data['description']
    if data.get('category') is not None:
        feed.category = data['category']
    if data.get('is_active') is not None:
        feed.is_active = data['is_active']

    db.session.commit()
    return jsonify({'message': 'Feed updated', 'feed': feed.to_dict()})


@feeds_bp.route('/<int:feed_id>', methods=['DELETE'])
def delete_feed(feed_id):
    """Delete a feed and its articles."""
    feed = Feed.query.get_or_404(feed_id)
    name = feed.name
    db.session.delete(feed)
    db.session.commit()
    return jsonify({'message': f'Feed "{name}" deleted'})


@feeds_bp.route('/<int:feed_id>/fetch', methods=['POST'])
def fetch_feed(feed_id):
    """Manually fetch articles for a feed."""
    feed = Feed.query.get_or_404(feed_id)

    try:
        new_count, updated_count = FeedFetcher.fetch_feed(feed)
        return jsonify({
            'message': 'Feed fetched',
            'feed': feed.to_dict(),
            'new_articles': new_count,
            'updated_articles': updated_count
        })
    except Exception as e:
        return jsonify({'error': f'Fetch failed: {str(e)}'}), 500


@feeds_bp.route('/fetch-all', methods=['POST'])
def fetch_all_feeds():
    """Fetch articles from all active feeds."""
    results = FeedFetcher.fetch_all_active()
    return jsonify({
        'message': 'All feeds fetched',
        'results': results
    })
