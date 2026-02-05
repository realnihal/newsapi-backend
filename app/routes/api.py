import os
from flask import Blueprint, request, jsonify
from sqlalchemy import desc, func
from datetime import datetime, timedelta
from app import db
from app.models import Feed, Article
from app.services import FeedFetcher

api_bp = Blueprint('api', __name__)


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get overall statistics."""
    total_feeds = Feed.query.count()
    active_feeds = Feed.query.filter_by(is_active=True).count()
    total_articles = Article.query.count()
    unread_articles = Article.query.filter_by(is_read=False).count()
    starred_articles = Article.query.filter_by(is_starred=True).count()

    # Articles in last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_articles = Article.query.filter(Article.fetched_at >= yesterday).count()

    return jsonify({
        'feeds': {
            'total': total_feeds,
            'active': active_feeds
        },
        'articles': {
            'total': total_articles,
            'unread': unread_articles,
            'starred': starred_articles,
            'last_24h': recent_articles
        }
    })


@api_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all categories with article counts."""
    categories = db.session.query(
        Feed.category,
        func.count(Article.id).label('article_count')
    ).outerjoin(Article).filter(
        Feed.category.isnot(None)
    ).group_by(Feed.category).all()

    return jsonify({
        'categories': [
            {'name': cat, 'article_count': count}
            for cat, count in categories
        ]
    })


@api_bp.route('/news', methods=['GET'])
def get_news():
    """
    Dynamic news API endpoint.

    Query params:
    - category: Filter by category
    - feed_id: Filter by feed
    - since: ISO timestamp - get articles published after this time
    - until: ISO timestamp - get articles published before this time
    - limit: Max articles to return (default 50, max 200)
    - offset: Skip first N articles
    - unread_only: Only return unread articles (true/false)
    """
    query = Article.query

    # Category filter
    category = request.args.get('category')
    if category:
        query = query.join(Feed).filter(Feed.category == category)

    # Feed filter
    feed_id = request.args.get('feed_id', type=int)
    if feed_id:
        query = query.filter(Article.feed_id == feed_id)

    # Time filters
    since = request.args.get('since')
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            query = query.filter(Article.published_at >= since_dt)
        except ValueError:
            pass

    until = request.args.get('until')
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
            query = query.filter(Article.published_at <= until_dt)
        except ValueError:
            pass

    # Unread filter
    unread_only = request.args.get('unread_only')
    if unread_only and unread_only.lower() == 'true':
        query = query.filter(Article.is_read == False)

    # Pagination
    limit = min(request.args.get('limit', 50, type=int), 200)
    offset = request.args.get('offset', 0, type=int)

    # Order and fetch
    query = query.order_by(desc(Article.published_at))
    total = query.count()
    articles = query.offset(offset).limit(limit).all()

    return jsonify({
        'news': [a.to_dict() for a in articles],
        'meta': {
            'total': total,
            'limit': limit,
            'offset': offset,
            'has_more': (offset + len(articles)) < total
        }
    })


@api_bp.route('/news/stream', methods=['GET'])
def get_news_stream():
    """
    Get a continuous stream format of news.
    Returns articles in a format suitable for streaming clients.
    """
    since = request.args.get('since')
    limit = min(request.args.get('limit', 100, type=int), 500)

    query = Article.query

    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            query = query.filter(Article.fetched_at > since_dt)
        except ValueError:
            pass

    articles = query.order_by(desc(Article.fetched_at)).limit(limit).all()

    # Get latest timestamp for next poll
    latest = articles[0].fetched_at if articles else datetime.utcnow()

    return jsonify({
        'items': [a.to_dict() for a in articles],
        'count': len(articles),
        'latest': latest.isoformat(),
        'poll_after': latest.isoformat()
    })


@api_bp.route('/refresh', methods=['POST'])
def refresh_feeds():
    """Trigger a refresh of all active feeds."""
    results = FeedFetcher.fetch_all_active()
    return jsonify({
        'message': 'Refresh complete',
        'new_articles': results['total_new'],
        'updated_articles': results['total_updated'],
        'feeds_processed': len(results['feeds']),
        'errors': len(results['errors'])
    })


@api_bp.route('/analysis/status', methods=['GET'])
def get_analysis_status():
    """Get the current status of article analysis."""
    from app.services.llm_client import LLMClientFactory

    # Get analysis statistics
    status_counts = db.session.query(
        Article.analysis_status,
        func.count(Article.id)
    ).group_by(Article.analysis_status).all()

    category_counts = db.session.query(
        Article.llm_category,
        func.count(Article.id)
    ).filter(
        Article.llm_category.isnot(None)
    ).group_by(Article.llm_category).all()

    # Calculate progress
    total = sum(count for _, count in status_counts)
    completed = next((count for status, count in status_counts if status == 'completed'), 0)
    pending = next((count for status, count in status_counts if status == 'pending'), 0)
    processing = next((count for status, count in status_counts if status == 'processing'), 0)
    failed = next((count for status, count in status_counts if status == 'failed'), 0)

    return jsonify({
        'llm_enabled': os.getenv('LLM_ENABLED', 'false').lower() == 'true',
        'llm_available': LLMClientFactory.is_available(),
        'llm_provider': os.getenv('LLM_PROVIDER', 'anthropic'),
        'progress': {
            'total': total,
            'completed': completed,
            'pending': pending,
            'processing': processing,
            'failed': failed,
            'percentage': round((completed / total * 100) if total > 0 else 0, 1)
        },
        'categories': {cat: count for cat, count in category_counts if cat}
    })


@api_bp.route('/analysis/trigger', methods=['POST'])
def trigger_analysis():
    """Manually trigger article analysis and topic creation."""
    from app.services.llm_client import LLMClientFactory
    from app.services.article_analyzer import ArticleAnalyzer
    from app.services.topic_analyzer import TopicAnalyzer

    if not LLMClientFactory.is_available():
        return jsonify({
            'error': 'LLM is not configured or available',
            'message': 'Set LLM_ENABLED=true and provide API key'
        }), 400

    # Get optional parameters
    limit = request.json.get('limit', 50) if request.json else 50
    create_topics = request.json.get('create_topics', True) if request.json else True

    try:
        # Analyze pending articles
        analyzer = ArticleAnalyzer()
        stats = analyzer.analyze_pending(limit=limit)

        result = {
            'message': 'Analysis complete',
            'analysis': stats,
            'topics_created': 0
        }

        # Create topics if requested and articles were analyzed
        if create_topics and stats['succeeded'] > 0:
            topics = TopicAnalyzer.create_topics(use_llm=True)
            result['topics_created'] = len(topics)

        return jsonify(result)

    except Exception as e:
        return jsonify({
            'error': 'Analysis failed',
            'message': str(e)
        }), 500
