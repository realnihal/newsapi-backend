import feedparser
import re
from html import unescape
from datetime import datetime
from time import mktime
from typing import Optional


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from text."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = unescape(text)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class RSSParser:
    """Parse RSS/Atom feeds and extract article data."""

    @staticmethod
    def parse(url: str) -> dict:
        """
        Parse an RSS/Atom feed from URL.

        Returns dict with feed info and list of entries.
        """
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            raise ValueError(f"Failed to parse feed: {feed.bozo_exception}")

        return {
            'feed': RSSParser._extract_feed_info(feed),
            'entries': [RSSParser._extract_entry(e) for e in feed.entries]
        }

    @staticmethod
    def _extract_feed_info(feed) -> dict:
        """Extract feed metadata."""
        return {
            'title': feed.feed.get('title', 'Untitled Feed'),
            'description': feed.feed.get('description', ''),
            'link': feed.feed.get('link', ''),
            'language': feed.feed.get('language', ''),
        }

    @staticmethod
    def _extract_thumbnail(entry) -> str:
        """Extract thumbnail image from various RSS feed formats."""
        # Try media:thumbnail
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url', '')

        # Try media:content
        if hasattr(entry, 'media_content') and entry.media_content:
            for media in entry.media_content:
                if media.get('medium') == 'image' or media.get('type', '').startswith('image'):
                    return media.get('url', '')
            # If no image type specified, try first media
            if entry.media_content[0].get('url'):
                return entry.media_content[0].get('url', '')

        # Try enclosure
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image'):
                    return enc.get('href', '') or enc.get('url', '')

        # Try to extract from content/description HTML
        content = ''
        if hasattr(entry, 'content') and entry.content:
            content = entry.content[0].get('value', '')
        elif hasattr(entry, 'summary'):
            content = entry.summary or ''

        if content:
            # Look for img tags
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
            if img_match:
                return img_match.group(1)

        # Try links with image type
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('image'):
                    return link.get('href', '')

        return ''

    @staticmethod
    def _extract_entry(entry) -> dict:
        """Extract article data from feed entry."""
        # Get unique identifier
        guid = entry.get('id') or entry.get('link') or entry.get('title', '')

        # Parse published date
        published = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            published = datetime.fromtimestamp(mktime(entry.published_parsed))
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            published = datetime.fromtimestamp(mktime(entry.updated_parsed))

        # Get content
        content = ''
        if hasattr(entry, 'content') and entry.content:
            content = entry.content[0].get('value', '')
        elif hasattr(entry, 'summary'):
            content = entry.summary

        # Get thumbnail
        thumbnail = RSSParser._extract_thumbnail(entry)

        # Validate thumbnail URL
        if thumbnail and not thumbnail.startswith(('http://', 'https://')):
            thumbnail = ''

        # Get and clean description - strip HTML
        raw_description = entry.get('summary', '') or ''
        description = strip_html(raw_description)[:1000]

        return {
            'guid': guid,
            'title': strip_html(entry.get('title', 'Untitled')),
            'link': entry.get('link', ''),
            'description': description,
            'content': content,
            'author': entry.get('author', ''),
            'published_at': published,
            'thumbnail': thumbnail,
        }
