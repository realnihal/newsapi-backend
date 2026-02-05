#!/usr/bin/env python3
"""Seed the database with default RSS feeds."""
import json
import os
import sys

# Add the parent directory to the path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.models import Feed


def load_default_feeds():
    """Load feeds from the default_feeds.json file."""
    feeds_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data',
        'default_feeds.json'
    )

    with open(feeds_file, 'r') as f:
        data = json.load(f)

    return data.get('feeds', [])


def seed_feeds(replace_existing=False):
    """
    Seed the database with default feeds.

    Args:
        replace_existing: If True, update existing feeds. If False, skip them.

    Returns:
        Dictionary with counts of added, updated, and skipped feeds.
    """
    app = create_app()

    with app.app_context():
        feeds_data = load_default_feeds()
        stats = {'added': 0, 'updated': 0, 'skipped': 0}

        for feed_data in feeds_data:
            # Check if feed already exists (by URL)
            existing = Feed.query.filter_by(url=feed_data['url']).first()

            if existing:
                if replace_existing:
                    existing.name = feed_data['name']
                    existing.category = feed_data.get('category')
                    existing.is_active = True
                    stats['updated'] += 1
                else:
                    stats['skipped'] += 1
            else:
                feed = Feed(
                    name=feed_data['name'],
                    url=feed_data['url'],
                    category=feed_data.get('category'),
                    is_active=True
                )
                db.session.add(feed)
                stats['added'] += 1

        db.session.commit()
        return stats


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Seed the database with default RSS feeds')
    parser.add_argument(
        '--replace',
        action='store_true',
        help='Update existing feeds instead of skipping them'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List feeds without adding them'
    )

    args = parser.parse_args()

    if args.list:
        feeds = load_default_feeds()
        print(f"\nDefault feeds ({len(feeds)} total):\n")
        for feed in feeds:
            print(f"  [{feed.get('category', 'General'):12}] {feed['name']}")
            print(f"                  {feed['url']}")
        return

    print("Seeding database with default feeds...")
    stats = seed_feeds(replace_existing=args.replace)

    print(f"\nResults:")
    print(f"  Added:   {stats['added']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"\nTotal feeds in JSON: {stats['added'] + stats['updated'] + stats['skipped']}")


if __name__ == '__main__':
    main()
