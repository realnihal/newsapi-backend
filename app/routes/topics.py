from flask import Blueprint, request, jsonify
from sqlalchemy import desc
from app import db
from app.models import Topic, ArticleTopic, Article
from app.services.topic_analyzer import TopicAnalyzer
from app.services.llm_client import LLMClientFactory
import logging

logger = logging.getLogger(__name__)

topics_bp = Blueprint('topics', __name__)


@topics_bp.route('', methods=['GET'])
def list_topics():
    """
    List all topics with optional filtering.

    Query params:
    - limit: Max topics to return (default 20)
    - include_articles: Include article list (default false)
    """
    limit = min(request.args.get('limit', 20, type=int), 50)
    include_articles = request.args.get('include_articles', 'false').lower() == 'true'

    topics = Topic.query.order_by(
        desc(Topic.article_count),
        desc(Topic.updated_at)
    ).limit(limit).all()

    return jsonify({
        'topics': [t.to_dict(include_articles=include_articles) for t in topics],
        'count': len(topics)
    })


@topics_bp.route('/<int:topic_id>', methods=['GET'])
def get_topic(topic_id):
    """Get a specific topic with its articles."""
    topic = Topic.query.get_or_404(topic_id)
    return jsonify({
        'topic': topic.to_dict(include_articles=True)
    })


@topics_bp.route('/analyze', methods=['POST'])
def analyze_topics():
    """
    Trigger topic analysis and clustering.

    Query params:
    - hours: How many hours of articles to analyze (default 24)
    """
    hours = request.args.get('hours', 24, type=int)

    try:
        topics = TopicAnalyzer.create_topics(hours=hours)
        return jsonify({
            'message': f'Created {len(topics)} topics',
            'topics': [t.to_dict() for t in topics]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@topics_bp.route('/refresh', methods=['POST'])
def refresh_topics():
    """Clear and regenerate all topics."""
    try:
        # Clear existing topics
        ArticleTopic.query.delete()
        Topic.query.delete()
        db.session.commit()

        # Regenerate
        topics = TopicAnalyzer.create_topics(hours=48)
        return jsonify({
            'message': f'Refreshed topics, created {len(topics)}',
            'topics': [t.to_dict() for t in topics]
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@topics_bp.route('/top', methods=['GET'])
def get_top_topics():
    """Get top topics for homepage display."""
    limit = min(request.args.get('limit', 10, type=int), 20)

    topics = Topic.query.filter(
        Topic.article_count >= 2
    ).order_by(
        desc(Topic.article_count),
        desc(Topic.updated_at)
    ).limit(limit).all()

    result = []
    for topic in topics:
        topic_dict = topic.to_dict()
        # Add source feeds
        sources = set()
        for at in topic.articles.limit(5).all():
            if at.article.feed:
                sources.add(at.article.feed.name)
        topic_dict['sources'] = list(sources)
        result.append(topic_dict)

    return jsonify({
        'topics': result,
        'count': len(result)
    })


@topics_bp.route('/<int:topic_id>/ask', methods=['POST'])
def ask_about_topic(topic_id):
    """
    Ask a question about a topic using AI.

    Request body:
    - question: The question to ask about the topic

    Returns:
    - answer: AI-generated answer based on the topic's articles
    - sources: List of articles used to generate the answer
    """
    topic = Topic.query.get_or_404(topic_id)
    data = request.get_json()

    if not data or not data.get('question'):
        return jsonify({'error': 'Question is required'}), 400

    question = data['question']

    # Check if LLM is available
    if not LLMClientFactory.is_available():
        return jsonify({
            'error': 'LLM not configured',
            'answer': 'AI Q&A is not available. Please configure an LLM provider (set LLM_ENABLED=true and provide API keys).'
        }), 503

    try:
        # Gather article context
        article_topics = topic.articles.limit(10).all()
        articles_context = []
        sources = []

        for at in article_topics:
            article = at.article
            articles_context.append({
                'title': article.title,
                'description': article.description or '',
                'source': article.feed.name if article.feed else 'Unknown',
                'published': article.published_at.isoformat() if article.published_at else ''
            })
            sources.append({
                'title': article.title,
                'source': article.feed.name if article.feed else 'Unknown',
                'link': article.link
            })

        # Build the prompt
        context_text = "\n\n".join([
            f"Article from {a['source']}:\nTitle: {a['title']}\n{a['description']}"
            for a in articles_context
        ])

        system_prompt = f"""You are a helpful news assistant. Answer questions based on the provided news articles about the topic "{topic.title}".

Be concise and factual. If the articles don't contain enough information to answer the question, say so.
Base your answer only on the provided articles, not on external knowledge.
Keep your response under 200 words."""

        user_prompt = f"""Here are news articles about "{topic.title}":

{context_text}

Question: {question}

Please provide a helpful, accurate answer based on these articles."""

        # Get LLM response
        llm = LLMClientFactory.create()
        answer = llm.complete(user_prompt, system=system_prompt, max_tokens=500)

        return jsonify({
            'answer': answer,
            'topic': topic.title,
            'sources': sources[:5]
        })

    except Exception as e:
        logger.error(f"Error in ask_about_topic: {e}")
        return jsonify({
            'error': str(e),
            'answer': 'Sorry, I encountered an error processing your question. Please try again.'
        }), 500


@topics_bp.route('/<int:topic_id>/similar', methods=['GET'])
def get_similar_articles(topic_id):
    """
    Get articles similar to those in this topic.

    Returns articles that share categories, entities, or keywords with the topic's articles.
    """
    topic = Topic.query.get_or_404(topic_id)
    limit = min(request.args.get('limit', 5, type=int), 10)

    # Get article IDs already in this topic
    topic_article_ids = [at.article_id for at in topic.articles.all()]

    if not topic_article_ids:
        return jsonify({'similar': [], 'count': 0})

    # Get the category of the topic
    topic_category = topic.category

    # Find similar articles not in this topic
    similar_query = Article.query.filter(
        Article.id.notin_(topic_article_ids)
    )

    # Filter by category if available
    if topic_category:
        similar_query = similar_query.filter(
            Article.llm_category == topic_category
        )

    similar_articles = similar_query.order_by(
        desc(Article.published_at)
    ).limit(limit).all()

    return jsonify({
        'similar': [
            {
                'id': a.id,
                'title': a.title,
                'thumbnail': a.thumbnail,
                'source': a.feed.name if a.feed else 'Unknown',
                'published_at': a.published_at.isoformat() if a.published_at else None,
                'link': a.link
            }
            for a in similar_articles
        ],
        'count': len(similar_articles)
    })


@topics_bp.route('/<int:topic_id>/images', methods=['GET'])
def get_topic_images(topic_id):
    """
    Get all images from articles in this topic.

    Returns a list of unique images from the topic's articles for gallery display.
    """
    topic = Topic.query.get_or_404(topic_id)
    limit = min(request.args.get('limit', 12, type=int), 20)

    images = []
    seen_urls = set()

    for at in topic.articles.all():
        article = at.article
        if article.thumbnail and article.thumbnail not in seen_urls:
            seen_urls.add(article.thumbnail)
            images.append({
                'url': article.thumbnail,
                'title': article.title,
                'source': article.feed.name if article.feed else 'Unknown',
                'article_link': article.link
            })
            if len(images) >= limit:
                break

    return jsonify({
        'images': images,
        'count': len(images),
        'topic_title': topic.title
    })
