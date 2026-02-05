import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


scheduler = BackgroundScheduler()


def init_scheduler(app):
    """Initialize the background scheduler for periodic feed fetching and analysis."""
    fetch_interval = int(os.getenv('FETCH_INTERVAL_MINUTES', 30))
    analyze_interval = int(os.getenv('ANALYZE_INTERVAL_MINUTES', 15))
    llm_enabled = os.getenv('LLM_ENABLED', 'false').lower() == 'true'

    def fetch_job():
        with app.app_context():
            from app.services import FeedFetcher
            results = FeedFetcher.fetch_all_active()
            app.logger.info(
                f"Scheduled fetch: {results['total_new']} new, "
                f"{results['total_updated']} updated, "
                f"{len(results['errors'])} errors"
            )

    def analyze_job():
        """Run LLM analysis on pending articles and create topics."""
        with app.app_context():
            from app.services.llm_client import LLMClientFactory
            from app.services.article_analyzer import ArticleAnalyzer
            from app.services.topic_analyzer import TopicAnalyzer

            if not LLMClientFactory.is_available():
                app.logger.debug("LLM not available, skipping analysis job")
                return

            try:
                # Step 1: Analyze pending articles
                analyzer = ArticleAnalyzer()
                stats = analyzer.analyze_pending(limit=50)
                app.logger.info(
                    f"Analysis job: processed={stats['processed']}, "
                    f"succeeded={stats['succeeded']}, failed={stats['failed']}"
                )

                # Step 2: Create/update topics if articles were analyzed
                if stats['succeeded'] > 0:
                    topics = TopicAnalyzer.create_topics(use_llm=True)
                    app.logger.info(f"Created {len(topics)} topics with LLM summaries")

            except Exception as e:
                app.logger.error(f"Analysis job failed: {e}")

    # Schedule feed fetching
    scheduler.add_job(
        fetch_job,
        trigger=IntervalTrigger(minutes=fetch_interval),
        id='fetch_feeds',
        name='Fetch RSS feeds',
        replace_existing=True
    )

    # Schedule LLM analysis (only if LLM is enabled)
    if llm_enabled:
        scheduler.add_job(
            analyze_job,
            trigger=IntervalTrigger(minutes=analyze_interval),
            id='analyze_articles',
            name='Analyze articles with LLM',
            replace_existing=True
        )
        app.logger.info(f"LLM analysis scheduled every {analyze_interval} minutes")

    scheduler.start()
    app.logger.info(f"Scheduler started: fetching every {fetch_interval} minutes")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
