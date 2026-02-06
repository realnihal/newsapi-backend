"""Semantic grouper service for LLM-powered topic clustering."""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from app import db
from app.models.article import Article
from app.models.topic import Topic, ArticleTopic
from app.services.llm_client import LLMClientFactory

logger = logging.getLogger(__name__)

GROUPING_SYSTEM_PROMPT = """You are a news analyst that groups related news articles into topics.
Given a list of article titles and descriptions, identify groups of articles that cover the same story or event.
For each group, provide:
1. A compelling topic title (not just copying an article title)
2. The article IDs that belong to this group
3. The category (Politics, Business, Technology, Science, Health, Sports, Entertainment, World, Environment, Opinion)
4. An importance score from 0.0 to 1.0 based on global significance

Only group articles that are clearly about the same specific story/event, not just the same general topic."""

SUMMARY_SYSTEM_PROMPT = """You are a storyteller who makes news irresistible.

Write summaries that:
- Lead with the most surprising, interesting, or consequential fact
- Use conversational, accessible language (not dry news-speak)
- Create curiosity that makes readers want to click through
- Are 2-3 sentences max

AVOID: Starting with "In a recent development..." or "According to reports..."
GOOD: "A single AI chatbot just passed the bar exam in all 50 states—and it only took 4 hours."
BAD: "Recent developments in AI technology have shown promising results in legal applications."

Be accurate but engaging. Write like you're telling a friend about something wild you just read."""


class SemanticGrouper:
    """Groups articles semantically using LLM analysis."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-load LLM client."""
        if self._client is None:
            self._client = LLMClientFactory.create()
        return self._client

    def group_articles(self, hours: int = 24, min_group_size: int = 2) -> List[Dict[str, Any]]:
        """
        Group analyzed articles by semantic similarity using LLM.

        Args:
            hours: Look back period in hours
            min_group_size: Minimum articles required to form a group

        Returns:
            List of topic groups with articles, title, category, and importance
        """
        since = datetime.utcnow() - timedelta(hours=hours)

        # Get analyzed articles
        articles = Article.query.filter(
            Article.fetched_at >= since,
            Article.analysis_status == 'completed'
        ).order_by(Article.published_at.desc()).limit(200).all()

        if len(articles) < min_group_size:
            logger.info(f"Not enough analyzed articles to group: {len(articles)}")
            return []

        # Prepare article data for grouping
        article_data = []
        for article in articles:
            article_data.append({
                "id": article.id,
                "title": article.title,
                "description": (article.description or "")[:300],
                "category": article.llm_category,
                "topics": article.llm_metadata.get("topics", []) if article.llm_metadata else [],
            })

        prompt = f"""Analyze these {len(articles)} news articles and group related ones:

{article_data}

Respond with JSON in this format:
{{
    "groups": [
        {{
            "title": "Descriptive Topic Title",
            "article_ids": [1, 2, 3],
            "category": "Politics",
            "importance": 0.8
        }}
    ]
}}

Rules:
- Only group articles that cover the SAME specific story/event
- Each article can only belong to one group
- Groups must have at least {min_group_size} articles
- Importance: 0.9-1.0 for major breaking news, 0.7-0.8 for significant news, 0.5-0.6 for regular news, below 0.5 for minor news"""

        try:
            result = self.client.complete_json(prompt, system=GROUPING_SYSTEM_PROMPT, max_tokens=2048)
            groups = result.get("groups", [])

            # Map article IDs back to Article objects
            article_map = {a.id: a for a in articles}
            processed_groups = []

            for group in groups:
                article_ids = group.get("article_ids", [])
                group_articles = [article_map[aid] for aid in article_ids if aid in article_map]

                if len(group_articles) >= min_group_size:
                    processed_groups.append({
                        "title": group.get("title", "News Update"),
                        "articles": group_articles,
                        "category": group.get("category"),
                        "importance": group.get("importance", 0.5),
                    })

            logger.info(f"Created {len(processed_groups)} semantic groups from {len(articles)} articles")
            return processed_groups

        except Exception as e:
            logger.error(f"Error grouping articles: {e}")
            return []

    def generate_topic_summary(self, articles: List[Article], title: str) -> str:
        """
        Generate an AI summary for a topic from its articles.

        Args:
            articles: List of articles in the topic
            title: Topic title for context

        Returns:
            AI-generated summary string
        """
        if not articles:
            return ""

        # Collect article content
        article_texts = []
        for article in articles[:5]:  # Use top 5 articles
            text = f"- {article.title}"
            if article.description:
                text += f": {article.description[:200]}"
            article_texts.append(text)

        prompt = f"""Topic: {title}

Articles:
{chr(10).join(article_texts)}

Write a 2-3 sentence summary that hooks readers immediately.
Lead with the most surprising or consequential fact. Make it conversational and compelling—like you're telling a friend about something fascinating you just discovered."""

        try:
            summary = self.client.complete(prompt, system=SUMMARY_SYSTEM_PROMPT, max_tokens=300)
            return summary.strip()
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            # Fallback to extractive summary
            return articles[0].description[:500] if articles[0].description else articles[0].title

    def create_topics_from_groups(self, groups: List[Dict[str, Any]]) -> List[Topic]:
        """
        Create Topic database entries from semantic groups.

        Args:
            groups: List of group dictionaries from group_articles()

        Returns:
            List of created Topic objects
        """
        created_topics = []

        for group in groups:
            articles = group["articles"]
            title = group["title"]

            # Generate AI summary
            llm_summary = self.generate_topic_summary(articles, title)

            # Extract keywords from article metadata
            all_topics = []
            for article in articles:
                if article.llm_metadata and "topics" in article.llm_metadata:
                    all_topics.extend(article.llm_metadata["topics"])

            # Get unique keywords
            keywords = list(dict.fromkeys(all_topics))[:10]

            # Get best thumbnail
            thumbnail = None
            for article in articles:
                if article.thumbnail:
                    thumbnail = article.thumbnail
                    break

            # Create topic
            topic = Topic(
                title=title,
                summary=llm_summary,  # Use LLM summary as main summary
                llm_summary=llm_summary,
                keywords=','.join(keywords),
                thumbnail=thumbnail,
                article_count=len(articles),
                category=group.get("category"),
                importance_score=group.get("importance", 0.5),
            )
            db.session.add(topic)
            db.session.flush()  # Get topic ID

            # Link articles to topic
            for i, article in enumerate(articles):
                link = ArticleTopic(
                    article_id=article.id,
                    topic_id=topic.id,
                    relevance_score=1.0 - (i * 0.05)  # Slightly decrease for later articles
                )
                db.session.add(link)

            created_topics.append(topic)

        db.session.commit()
        logger.info(f"Created {len(created_topics)} topics with AI summaries")
        return created_topics
