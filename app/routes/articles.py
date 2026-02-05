from flask import Blueprint, request, jsonify
from sqlalchemy import desc
from app import db
from app.models import Article, Feed

articles_bp = Blueprint('articles', __name__)


@articles_bp.route('', methods=['GET'])
def list_articles():
    """
    List articles with filtering and pagination.

    Query params:
    - feed_id: Filter by feed
    - category: Filter by feed category
    - is_read: Filter by read status (true/false)
    - is_starred: Filter by starred status (true/false)
    - search: Search in title and description
    - page: Page number (default 1)
    - per_page: Items per page (default 20, max 100)
    """
    query = Article.query

    # Filters
    feed_id = request.args.get('feed_id', type=int)
    if feed_id:
        query = query.filter(Article.feed_id == feed_id)

    category = request.args.get('category')
    if category:
        query = query.join(Feed).filter(Feed.category == category)

    is_read = request.args.get('is_read')
    if is_read is not None:
        query = query.filter(Article.is_read == (is_read.lower() == 'true'))

    is_starred = request.args.get('is_starred')
    if is_starred is not None:
        query = query.filter(Article.is_starred == (is_starred.lower() == 'true'))

    search = request.args.get('search')
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Article.title.ilike(search_term),
                Article.description.ilike(search_term)
            )
        )

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    # Order by published date (newest first)
    query = query.order_by(desc(Article.published_at))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'articles': [a.to_dict() for a in pagination.items],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })


@articles_bp.route('/latest', methods=['GET'])
def latest_articles():
    """Get the latest articles across all feeds."""
    limit = min(request.args.get('limit', 50, type=int), 100)

    articles = Article.query.order_by(
        desc(Article.published_at)
    ).limit(limit).all()

    return jsonify({
        'articles': [a.to_dict() for a in articles],
        'count': len(articles)
    })


@articles_bp.route('/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """Get a specific article with full content."""
    article = Article.query.get_or_404(article_id)
    return jsonify({'article': article.to_dict(include_content=True)})


@articles_bp.route('/<int:article_id>/read', methods=['POST'])
def mark_read(article_id):
    """Mark article as read."""
    article = Article.query.get_or_404(article_id)
    article.is_read = True
    db.session.commit()
    return jsonify({'message': 'Marked as read', 'article': article.to_dict()})


@articles_bp.route('/<int:article_id>/unread', methods=['POST'])
def mark_unread(article_id):
    """Mark article as unread."""
    article = Article.query.get_or_404(article_id)
    article.is_read = False
    db.session.commit()
    return jsonify({'message': 'Marked as unread', 'article': article.to_dict()})


@articles_bp.route('/<int:article_id>/star', methods=['POST'])
def star_article(article_id):
    """Star/favorite an article."""
    article = Article.query.get_or_404(article_id)
    article.is_starred = True
    db.session.commit()
    return jsonify({'message': 'Article starred', 'article': article.to_dict()})


@articles_bp.route('/<int:article_id>/unstar', methods=['POST'])
def unstar_article(article_id):
    """Unstar an article."""
    article = Article.query.get_or_404(article_id)
    article.is_starred = False
    db.session.commit()
    return jsonify({'message': 'Article unstarred', 'article': article.to_dict()})


@articles_bp.route('/mark-all-read', methods=['POST'])
def mark_all_read():
    """Mark all articles as read, optionally filtered by feed_id."""
    feed_id = request.args.get('feed_id', type=int)

    query = Article.query.filter(Article.is_read == False)
    if feed_id:
        query = query.filter(Article.feed_id == feed_id)

    count = query.update({'is_read': True})
    db.session.commit()

    return jsonify({'message': f'Marked {count} articles as read'})
