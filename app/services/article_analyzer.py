"""Article analyzer service using LLM for content analysis."""
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from app import db
from app.models.article import Article
from app.services.llm_client import LLMClientFactory

logger = logging.getLogger(__name__)

# Categories for classification
CATEGORIES = [
    "Politics",
    "Business",
    "Technology",
    "Science",
    "Health",
    "Sports",
    "Entertainment",
    "World",
    "Environment",
    "Opinion",
]

ANALYSIS_SYSTEM_PROMPT = """You are a news article analyzer. For each article, extract:
1. category: One of [Politics, Business, Technology, Science, Health, Sports, Entertainment, World, Environment, Opinion]
2. sentiment: One of [positive, negative, neutral]
3. entities: List of key people, organizations, and places mentioned
4. topics: List of 3-5 topic keywords
5. key_facts: List of 2-3 key facts from the article

Respond with a JSON array containing analysis for each article."""


class ArticleAnalyzer:
    """Analyzes articles using LLM to extract categories, sentiment, entities, etc."""

    def __init__(self, batch_size: int = 10):
        self.batch_size = batch_size
        self._client = None

    @property
    def client(self):
        """Lazy-load LLM client."""
        if self._client is None:
            self._client = LLMClientFactory.create()
        return self._client

    @staticmethod
    def compute_content_hash(article: Article) -> str:
        """Compute SHA-256 hash of article content for change detection."""
        content = f"{article.title}|{article.description or ''}|{article.content or ''}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def analyze_batch(self, articles: List[Article]) -> List[Dict[str, Any]]:
        """
        Analyze a batch of articles using a single LLM call.

        Args:
            articles: List of Article objects to analyze (max 10 recommended)

        Returns:
            List of analysis results, one per article
        """
        if not articles:
            return []

        # Prepare article summaries for the prompt
        article_summaries = []
        for i, article in enumerate(articles):
            summary = {
                "id": i,
                "title": article.title,
                "description": (article.description or "")[:500],  # Truncate for token efficiency
            }
            article_summaries.append(summary)

        prompt = f"""Analyze these {len(articles)} news articles:

{article_summaries}

For each article (identified by id), provide analysis in this JSON format:
{{
    "analyses": [
        {{
            "id": 0,
            "category": "Politics",
            "sentiment": "neutral",
            "entities": ["Person Name", "Organization"],
            "topics": ["topic1", "topic2", "topic3"],
            "key_facts": ["fact 1", "fact 2"]
        }}
    ]
}}"""

        try:
            result = self.client.complete_json(prompt, system=ANALYSIS_SYSTEM_PROMPT, max_tokens=2048)
            return result.get("analyses", [])
        except Exception as e:
            logger.error(f"Error analyzing batch: {e}")
            return []

    def analyze_pending(self, limit: int = 50) -> Dict[str, Any]:
        """
        Process pending articles in batches.

        Args:
            limit: Maximum number of articles to process

        Returns:
            Statistics about the analysis run
        """
        stats = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
        }

        # Get pending articles
        pending_articles = Article.query.filter(
            Article.analysis_status == 'pending'
        ).order_by(Article.fetched_at.desc()).limit(limit).all()

        if not pending_articles:
            logger.info("No pending articles to analyze")
            return stats

        logger.info(f"Found {len(pending_articles)} pending articles to analyze")

        # Process in batches
        for i in range(0, len(pending_articles), self.batch_size):
            batch = pending_articles[i:i + self.batch_size]

            # Mark as processing
            for article in batch:
                article.analysis_status = 'processing'
            db.session.commit()

            # Analyze batch
            results = self.analyze_batch(batch)

            # Apply results
            for j, article in enumerate(batch):
                stats["processed"] += 1

                # Check if content has changed
                new_hash = self.compute_content_hash(article)
                if article.content_hash == new_hash and article.analyzed_at:
                    article.analysis_status = 'completed'
                    stats["skipped"] += 1
                    continue

                # Find matching result
                result = None
                for r in results:
                    if r.get("id") == j:
                        result = r
                        break

                if result:
                    article.llm_category = result.get("category")
                    article.llm_sentiment = result.get("sentiment")
                    article.llm_metadata = {
                        "entities": result.get("entities", []),
                        "topics": result.get("topics", []),
                        "key_facts": result.get("key_facts", []),
                    }
                    article.content_hash = new_hash
                    article.analyzed_at = datetime.utcnow()
                    article.analysis_status = 'completed'
                    stats["succeeded"] += 1
                else:
                    article.analysis_status = 'failed'
                    stats["failed"] += 1

            db.session.commit()

        logger.info(f"Analysis complete: {stats}")
        return stats

    def reanalyze_changed(self) -> int:
        """
        Find articles whose content has changed and mark them for reanalysis.

        Returns:
            Number of articles marked for reanalysis
        """
        count = 0
        articles = Article.query.filter(
            Article.analysis_status == 'completed'
        ).all()

        for article in articles:
            new_hash = self.compute_content_hash(article)
            if article.content_hash != new_hash:
                article.analysis_status = 'pending'
                count += 1

        db.session.commit()
        logger.info(f"Marked {count} articles for reanalysis")
        return count

    def get_analysis_stats(self) -> Dict[str, Any]:
        """Get statistics about article analysis status."""
        from sqlalchemy import func

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

        return {
            "by_status": {status: count for status, count in status_counts},
            "by_category": {cat: count for cat, count in category_counts},
        }
