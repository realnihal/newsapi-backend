import os
import re
from html import unescape
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional
import logging
from app import db
from app.models.article import Article
from app.models.topic import Topic, ArticleTopic

logger = logging.getLogger(__name__)


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from text."""
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Common stop words to filter out
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
    'shall', 'can', 'need', 'dare', 'ought', 'used', 'this', 'that', 'these', 'those',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who', 'whom',
    'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
    'than', 'too', 'very', 'just', 'also', 'now', 'new', 'said', 'says', 'say',
    'about', 'after', 'before', 'between', 'into', 'through', 'during', 'above',
    'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then',
    'once', 'here', 'there', 'any', 'many', 'much', 'get', 'got', 'its', 'his', 'her',
    'their', 'our', 'your', 'my', 'me', 'him', 'us', 'them', 'being', 'having',
    'while', 'although', 'though', 'because', 'since', 'unless', 'until', 'if',
    'whether', 'even', 'still', 'already', 'yet', 'ever', 'never', 'always',
    'often', 'sometimes', 'usually', 'really', 'actually', 'probably', 'perhaps',
    'maybe', 'certainly', 'definitely', 'however', 'therefore', 'thus', 'hence',
    'meanwhile', 'moreover', 'furthermore', 'nevertheless', 'nonetheless',
    'one', 'two', 'first', 'last', 'next', 'previous', 'former', 'latter',
    'make', 'made', 'take', 'took', 'come', 'came', 'go', 'went', 'see', 'saw',
    'know', 'knew', 'think', 'thought', 'find', 'found', 'give', 'gave', 'tell', 'told',
    'ask', 'asked', 'use', 'used', 'try', 'tried', 'leave', 'left', 'call', 'called',
    'keep', 'kept', 'let', 'begin', 'began', 'seem', 'seemed', 'help', 'helped',
    'show', 'showed', 'hear', 'heard', 'play', 'played', 'run', 'ran', 'move', 'moved',
    'live', 'lived', 'believe', 'believed', 'hold', 'held', 'bring', 'brought',
    'happen', 'happened', 'write', 'wrote', 'provide', 'provided', 'sit', 'sat',
    'stand', 'stood', 'lose', 'lost', 'pay', 'paid', 'meet', 'met', 'include', 'included',
    'continue', 'continued', 'set', 'learn', 'learned', 'change', 'changed', 'lead', 'led',
    'understand', 'understood', 'watch', 'watched', 'follow', 'followed', 'stop', 'stopped',
    'create', 'created', 'speak', 'spoke', 'read', 'allow', 'allowed', 'add', 'added',
    'spend', 'spent', 'grow', 'grew', 'open', 'opened', 'walk', 'walked', 'win', 'won',
    'offer', 'offered', 'remember', 'remembered', 'love', 'loved', 'consider', 'considered',
    'appear', 'appeared', 'buy', 'bought', 'wait', 'waited', 'serve', 'served', 'die', 'died',
    'send', 'sent', 'expect', 'expected', 'build', 'built', 'stay', 'stayed', 'fall', 'fell',
    'cut', 'reach', 'reached', 'kill', 'killed', 'remain', 'remained', 'suggest', 'suggested',
    'raise', 'raised', 'pass', 'passed', 'sell', 'sold', 'require', 'required', 'report', 'reported',
    'decide', 'decided', 'pull', 'pulled', 'like', 'liked', 'bbc', 'news', 'reuters', 'ap',
    'cnn', 'nyt', 'times', 'post', 'guardian', 'abc', 'nbc', 'cbs', 'fox'
}


class TopicAnalyzer:
    """Analyzes articles and groups them into topics."""

    @staticmethod
    def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
        """Extract important keywords from text."""
        if not text:
            return []

        # Clean and tokenize
        text = text.lower()
        text = re.sub(r'<[^>]+>', ' ', text)  # Remove HTML
        text = re.sub(r'[^\w\s]', ' ', text)  # Remove punctuation
        words = text.split()

        # Filter stop words and short words
        words = [w for w in words if w not in STOP_WORDS and len(w) > 2]

        # Count and get most common
        word_counts = Counter(words)
        return [word for word, _ in word_counts.most_common(max_keywords)]

    @staticmethod
    def calculate_similarity(keywords1: Set[str], keywords2: Set[str]) -> float:
        """Calculate Jaccard similarity between two keyword sets."""
        if not keywords1 or not keywords2:
            return 0.0
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def generate_summary(articles: List[Article], max_sentences: int = 3) -> str:
        """Generate a summary from multiple articles using extractive summarization."""
        all_sentences = []

        for article in articles[:5]:  # Use top 5 articles
            text = strip_html(article.description or article.title)
            # Split into sentences
            sentences = re.split(r'[.!?]+', text)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) > 30 and len(sent) < 300:
                    all_sentences.append(sent)

        if not all_sentences:
            return strip_html(articles[0].title) if articles else ""

        # Score sentences by keyword frequency
        all_text = ' '.join([strip_html(a.title + ' ' + (a.description or '')) for a in articles])
        keywords = set(TopicAnalyzer.extract_keywords(all_text, 20))

        scored = []
        for sent in all_sentences:
            words = set(sent.lower().split())
            score = len(words & keywords)
            scored.append((score, sent))

        # Get top sentences
        scored.sort(reverse=True)
        top_sentences = [sent for _, sent in scored[:max_sentences]]

        return '. '.join(top_sentences) + '.' if top_sentences else ""

    @staticmethod
    def generate_topic_title_llm(articles: List[Article]) -> Tuple[str, str]:
        """Generate title and summary using LLM."""
        try:
            from app.services.llm_client import LLMClientFactory
            if not LLMClientFactory.is_available():
                return None, None

            client = LLMClientFactory.create()

            # Prepare article info
            article_info = []
            for a in articles[:5]:
                title = strip_html(a.title)
                desc = strip_html(a.description or '')[:200]
                article_info.append(f"- {title}: {desc}")

            prompt = f"""Based on these related news articles, generate:
1. A catchy, engaging topic title (max 10 words) that hooks readers
2. A 2-sentence summary that leads with the most interesting fact

Articles:
{chr(10).join(article_info)}

Respond in JSON format:
{{"title": "Your Catchy Title Here", "summary": "Lead with the hook. Follow with key details."}}"""

            system = """You are a viral news editor crafting headlines that people can't help but click.

For TITLES:
- Hook readers with intrigue, surprise, or emotion
- Be specific and concrete, not vague
- Use active verbs and vivid language
- AVOID: "Breaking:", "Latest:", "Update:", "Report:", or any generic news-speak
- AVOID: Bland phrases like "announces", "reveals", "amid concerns"
- Good: "Tesla's Secret Factory Churns Out Robots at Midnight"
- Bad: "Tesla Announces New Robotics Manufacturing Facility"

Be factual but compelling. Make readers curious."""
            result = client.complete_json(prompt, system=system, max_tokens=200)

            return result.get('title'), result.get('summary')
        except Exception as e:
            logger.error(f"LLM title generation failed: {e}")
            return None, None

    @staticmethod
    def generate_topic_title(articles: List[Article], keywords: List[str]) -> str:
        """Generate a title for the topic cluster using the lead article's headline."""
        if not articles:
            return "News Update"

        # Try LLM first
        llm_title, _ = TopicAnalyzer.generate_topic_title_llm(articles)
        if llm_title:
            return llm_title

        # Use the lead article's title — it's the most descriptive option
        lead_title = strip_html(articles[0].title).strip()
        if lead_title:
            # Truncate very long titles at a natural break
            if len(lead_title) > 80:
                # Try to cut at a natural boundary
                for sep in [' - ', ' | ', ': ', ' — ']:
                    if sep in lead_title[:80]:
                        lead_title = lead_title[:lead_title.index(sep)]
                        break
                else:
                    lead_title = lead_title[:77].rsplit(' ', 1)[0] + '...'
            return lead_title

        return "News Update"

    @staticmethod
    def cluster_articles(hours: int = 24, similarity_threshold: float = 0.25) -> List[Dict]:
        """Cluster recent articles into topics."""
        # Get recent articles
        since = datetime.utcnow() - timedelta(hours=hours)
        articles = Article.query.filter(
            Article.fetched_at >= since
        ).order_by(Article.published_at.desc()).all()

        if not articles:
            return []

        # Extract keywords for each article
        article_keywords = {}
        for article in articles:
            text = f"{article.title} {article.description or ''}"
            keywords = set(TopicAnalyzer.extract_keywords(text, 15))
            article_keywords[article.id] = keywords

        # Cluster articles
        clusters = []
        clustered_ids = set()

        for article in articles:
            if article.id in clustered_ids:
                continue

            # Start new cluster
            cluster = [article]
            cluster_keywords = article_keywords[article.id].copy()
            clustered_ids.add(article.id)

            # Find similar articles
            for other in articles:
                if other.id in clustered_ids:
                    continue

                similarity = TopicAnalyzer.calculate_similarity(
                    cluster_keywords,
                    article_keywords[other.id]
                )

                if similarity >= similarity_threshold:
                    cluster.append(other)
                    cluster_keywords |= article_keywords[other.id]
                    clustered_ids.add(other.id)

            clusters.append({
                'articles': cluster,
                'keywords': list(cluster_keywords)[:10]
            })

        return clusters

    @staticmethod
    def create_topics(hours: int = 24, use_llm: bool = None) -> List[Topic]:
        """
        Create topic entries from article clusters.

        Args:
            hours: Look back period in hours
            use_llm: If True, use LLM-powered semantic grouping. If None, check LLM_ENABLED env var.

        Returns:
            List of created Topic objects
        """
        # Determine if we should use LLM
        if use_llm is None:
            use_llm = os.getenv('LLM_ENABLED', 'false').lower() == 'true'

        # Clear old topics (older than 48 hours)
        old_date = datetime.utcnow() - timedelta(hours=48)
        ArticleTopic.query.filter(
            ArticleTopic.topic_id.in_(
                db.session.query(Topic.id).filter(Topic.created_at < old_date)
            )
        ).delete(synchronize_session=False)
        Topic.query.filter(Topic.created_at < old_date).delete()
        db.session.commit()

        # Use LLM-powered semantic grouping if enabled and available
        if use_llm:
            try:
                from app.services.llm_client import LLMClientFactory
                if LLMClientFactory.is_available():
                    logger.info("Using LLM-powered semantic grouping")
                    from app.services.semantic_grouper import SemanticGrouper
                    grouper = SemanticGrouper()
                    groups = grouper.group_articles(hours=hours)
                    if groups:
                        return grouper.create_topics_from_groups(groups)
                    else:
                        logger.info("No semantic groups found, falling back to keyword clustering")
                else:
                    logger.info("LLM not available, falling back to keyword clustering")
            except Exception as e:
                logger.error(f"LLM grouping failed, falling back to keywords: {e}")

        # Fallback to keyword-based clustering
        logger.info("Using keyword-based clustering")
        clusters = TopicAnalyzer.cluster_articles(hours=hours)

        created_topics = []
        for cluster_data in clusters:
            articles = cluster_data['articles']
            keywords = cluster_data['keywords']

            # Try to get LLM-generated title and summary
            llm_title, llm_summary = TopicAnalyzer.generate_topic_title_llm(articles)

            # Use LLM results or fall back to extractive methods
            title = llm_title or TopicAnalyzer.generate_topic_title(articles, keywords)
            summary = llm_summary or TopicAnalyzer.generate_summary(articles)

            # Get best thumbnail - prefer valid image URLs
            thumbnail = None
            for article in articles:
                if article.thumbnail and article.thumbnail.startswith(('http://', 'https://')):
                    # Skip very small images or icons
                    if 'icon' not in article.thumbnail.lower() and 'logo' not in article.thumbnail.lower():
                        thumbnail = article.thumbnail
                        break

            # If no good thumbnail found, try any valid URL
            if not thumbnail:
                for article in articles:
                    if article.thumbnail and article.thumbnail.startswith(('http://', 'https://')):
                        thumbnail = article.thumbnail
                        break

            # Create topic
            topic = Topic(
                title=title,
                summary=summary,
                llm_summary=llm_summary,
                keywords=','.join(keywords),
                thumbnail=thumbnail,
                article_count=len(articles),
                importance_score=0.5,  # Default importance for keyword-based topics
            )
            db.session.add(topic)
            db.session.flush()  # Get the topic ID

            # Link articles to topic
            for i, article in enumerate(articles):
                link = ArticleTopic(
                    article_id=article.id,
                    topic_id=topic.id,
                    relevance_score=1.0 - (i * 0.1)  # Decrease score for later articles
                )
                db.session.add(link)

            created_topics.append(topic)

        db.session.commit()
        return created_topics
