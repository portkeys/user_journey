"""
Event Analyzer - Generic User Event Analysis
Refactored from robin_analyzer.py for multi-user support
"""

import json
import re
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from urllib.parse import urlparse
from typing import Any, Optional

import pandas as pd


def parse_stringified_array(value):
    """Parse stringified arrays like '[tag1, tag2]' or '[Name One, Name Two]'"""
    if not value or value == 'null' or value == '[]':
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except:
            pass
        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1]
            if inner:
                items = [item.strip() for item in inner.split(',')]
                return [item for item in items if item]
    return []


class EventAnalyzer:
    """Generic analyzer for Outside Online user event data"""

    def __init__(self, events: list, user_config: Optional[dict] = None):
        """
        Initialize analyzer with events and optional user config.

        Args:
            events: List of event dictionaries
            user_config: Optional dict with user metadata (display_name, timezone_offset, etc.)
        """
        self.events = events
        self.user_config = user_config or {}
        self.summary = {}

    def analyze_publications(self) -> dict:
        """Analyze distribution by publication (DOMAIN field)"""
        domains = Counter()
        for event in self.events:
            domain = event.get('DOMAIN') or 'unknown'
            domains[domain] += 1

        self.summary['publications'] = dict(domains)
        return dict(domains)

    def extract_tags(self) -> dict:
        """Extract and analyze tags from TAGS field"""
        all_tags = Counter()
        events_with_tags = 0

        for event in self.events:
            tags_raw = event.get('TAGS')
            tags = parse_stringified_array(tags_raw)
            if tags:
                events_with_tags += 1
                for tag in tags:
                    if tag and isinstance(tag, str):
                        all_tags[tag.lower().strip()] += 1

        self.summary['tags'] = dict(all_tags.most_common(200))
        self.summary['events_with_tags'] = events_with_tags
        return dict(all_tags)

    def analyze_authors(self) -> dict:
        """Analyze authors from AUTHORS field"""
        authors = Counter()
        for event in self.events:
            authors_raw = event.get('AUTHORS')
            author_list = parse_stringified_array(authors_raw)
            for author in author_list:
                if author and isinstance(author, str):
                    authors[author.strip()] += 1

        self.summary['authors'] = dict(authors.most_common(100))
        return dict(authors)

    def analyze_content_categories(self) -> dict:
        """Extract content categories from URL paths"""
        categories = Counter()
        subcategories = Counter()

        for event in self.events:
            path = event.get('PATH', '')
            if path and path.startswith('/'):
                parts = [p for p in path.split('/') if p]
                if parts:
                    categories[parts[0]] += 1
                    if len(parts) >= 2:
                        subcat = f"{parts[0]}/{parts[1]}"
                        subcategories[subcat] += 1

        self.summary['content_categories'] = dict(categories)
        self.summary['subcategories'] = dict(subcategories.most_common(100))
        return {'categories': dict(categories), 'subcategories': dict(subcategories)}

    def analyze_domains_visited(self) -> dict:
        """Analyze actual website domains from URLs"""
        domains = Counter()
        for event in self.events:
            url = event.get('URL') or event.get('PAGE_URL')
            if url and url.startswith('http'):
                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                    if domain.startswith('www.'):
                        domain = domain[4:]
                    if domain:
                        domains[domain] += 1
                except:
                    pass

        self.summary['website_domains'] = dict(domains)
        return dict(domains)

    def analyze_referrers(self) -> dict:
        """Analyze traffic sources from REFERRER field"""
        referrer_domains = Counter()

        for event in self.events:
            referrer = event.get('REFERRER', '')
            if referrer and referrer.startswith('http'):
                try:
                    parsed = urlparse(referrer)
                    domain = parsed.netloc.lower()
                    if domain.startswith('www.'):
                        domain = domain[4:]
                    if domain:
                        referrer_domains[domain] += 1
                except:
                    pass

        # Check for email/newsletter traffic
        email_patterns = ['newsletter', 'email', 'utm_medium=email', 'utm_source=newsletter']
        email_traffic = 0
        for event in self.events:
            url = event.get('URL') or ''
            if url and any(p in url.lower() for p in email_patterns):
                email_traffic += 1

        self.summary['referrer_domains'] = dict(referrer_domains.most_common(50))
        self.summary['email_traffic_count'] = email_traffic
        return {'domains': dict(referrer_domains), 'email_traffic': email_traffic}

    def analyze_temporal_patterns(self) -> dict:
        """Analyze temporal patterns using TIMESTAMP field"""
        timestamps = []
        for event in self.events:
            ts_str = event.get('TIMESTAMP')
            if ts_str:
                try:
                    ts = pd.to_datetime(ts_str)
                    timestamps.append(ts)
                except:
                    pass

        if not timestamps:
            return {}

        timestamps = sorted(timestamps)

        # Events by hour of day (UTC)
        hours = Counter([ts.hour for ts in timestamps])

        # Events by day of week
        days = Counter([ts.day_name() for ts in timestamps])

        # Events by month
        months = Counter([ts.strftime('%Y-%m') for ts in timestamps])

        # Recent activity
        now = timestamps[-1]
        last_7_days = [ts for ts in timestamps if ts > now - timedelta(days=7)]
        last_30_days = [ts for ts in timestamps if ts > now - timedelta(days=30)]

        self.summary['temporal'] = {
            'first_event': str(timestamps[0]),
            'last_event': str(timestamps[-1]),
            'total_days': (timestamps[-1] - timestamps[0]).days,
            'events_last_7_days': len(last_7_days),
            'events_last_30_days': len(last_30_days),
            'avg_events_per_day': len(self.events) / max((timestamps[-1] - timestamps[0]).days, 1),
            'by_hour': dict(hours),
            'by_day_of_week': dict(days),
            'by_month': dict(months),
        }

        return self.summary['temporal']

    def analyze_article_engagement(self) -> dict:
        """Analyze article-level engagement patterns"""
        articles = Counter()
        for event in self.events:
            title = event.get('TITLE')
            url = event.get('URL')
            if title and url:
                articles[(title, url)] += 1

        multi_read = [(k, v) for k, v in articles.items() if v > 1]
        single_read = [(k, v) for k, v in articles.items() if v == 1]

        # Content type indicators
        how_to = sum(1 for e in self.events if 'how to' in (e.get('TITLE') or '').lower())
        best_of = sum(1 for e in self.events if 'best' in (e.get('TITLE') or '').lower())
        reviews = sum(1 for e in self.events if 'review' in (e.get('TITLE') or '').lower())
        guides = sum(1 for e in self.events if 'guide' in (e.get('TITLE') or '').lower())

        self.summary['article_engagement'] = {
            'unique_articles': len(articles),
            'single_read': len(single_read),
            'multi_read': len(multi_read),
            'most_revisited': [(title, count) for (title, url), count in sorted(multi_read, key=lambda x: -x[1])[:30]],
            'content_types': {
                'how_to': how_to,
                'best_lists': best_of,
                'reviews': reviews,
                'guides': guides,
            }
        }

        return self.summary['article_engagement']

    def analyze_ecosystem_usage(self) -> dict:
        """Analyze usage across Outside ecosystem (apps, web, watch)"""
        ecosystem = {
            'trailforks': {'web': 0, 'app': 0, 'ridelogs': 0, 'map_views': 0, 'photos': 0, 'unique_rides': 0},
            'gaia_gps': {'events': 0},
            'outside_app': {'events': 0},
            'outside_watch': {'events': 0},
            'editorial': {'events': 0, 'articles': 0},
            'devices': {'events': 0},
            'monthly_app_usage': defaultdict(lambda: defaultdict(int))
        }

        ridelog_ids = set()

        for event in self.events:
            domain = (event.get('DOMAIN') or '').lower()
            path = event.get('PATH') or ''
            module = event.get('MODULE') or ''
            content_type = event.get('CONTENT_TYPE') or ''
            ts = event.get('TIMESTAMP')

            month = None
            if ts:
                try:
                    month = pd.to_datetime(ts).strftime('%Y-%m')
                except:
                    pass

            # Trailforks
            if 'trailfork' in domain:
                if 'app' in domain:
                    ecosystem['trailforks']['app'] += 1
                    if month:
                        ecosystem['monthly_app_usage'][month]['trailforks_app'] += 1
                else:
                    ecosystem['trailforks']['web'] += 1
                    if month:
                        ecosystem['monthly_app_usage'][month]['trailforks_web'] += 1

                if '/ridelog' in path or module == 'ridelog' or content_type == 'ridelog':
                    ecosystem['trailforks']['ridelogs'] += 1
                    match = re.search(r'/ridelog/view/(\d+)', path)
                    if match:
                        ridelog_ids.add(match.group(1))
                if '/map' in path or module == 'map':
                    ecosystem['trailforks']['map_views'] += 1
                if content_type == 'photo':
                    ecosystem['trailforks']['photos'] += 1

            # Gaia GPS
            elif 'gaia' in domain:
                ecosystem['gaia_gps']['events'] += 1
                if month:
                    ecosystem['monthly_app_usage'][month]['gaia_gps'] += 1

            # Outside App
            elif domain == 'outside app':
                ecosystem['outside_app']['events'] += 1
                if month:
                    ecosystem['monthly_app_usage'][month]['outside_app'] += 1

            # Outside Watch
            elif 'watch' in domain:
                ecosystem['outside_watch']['events'] += 1
                if month:
                    ecosystem['monthly_app_usage'][month]['outside_watch'] += 1

            # Devices
            elif domain == 'devices':
                ecosystem['devices']['events'] += 1

            # Editorial sites
            else:
                editorial_domains = ['velonews', 'outside-online', 'backpacker', 'run',
                                   'trailrunner', 'triathlete', 'ski', 'climbing',
                                   'yogajournal', 'oxygen', 'nationalparktrips', 'www.outsideonline']
                if any(ed in domain for ed in editorial_domains) or domain == 'unknown':
                    ecosystem['editorial']['events'] += 1
                    if event.get('TITLE'):
                        ecosystem['editorial']['articles'] += 1

        ecosystem['trailforks']['unique_rides'] = len(ridelog_ids)
        ecosystem['monthly_app_usage'] = {k: dict(v) for k, v in ecosystem['monthly_app_usage'].items()}

        self.summary['ecosystem'] = ecosystem
        return ecosystem

    def calculate_engagement_metrics(self) -> dict:
        """Calculate overall engagement metrics"""
        temporal = self.summary.get('temporal', {})
        total_days = temporal.get('total_days', 1) or 1

        metrics = {
            'total_events': len(self.events),
            'total_days_tracked': total_days,
            'events_per_day': len(self.events) / total_days,
            'unique_publications': len(self.summary.get('publications', {})),
            'unique_tags_encountered': len(self.summary.get('tags', {})),
            'unique_authors_read': len(self.summary.get('authors', {})),
            'unique_articles': self.summary.get('article_engagement', {}).get('unique_articles', 0),
        }

        self.summary['engagement_metrics'] = metrics
        return metrics

    def run_full_analysis(self) -> dict:
        """Run complete analysis pipeline"""
        self.analyze_publications()
        self.extract_tags()
        self.analyze_authors()
        self.analyze_content_categories()
        self.analyze_domains_visited()
        self.analyze_referrers()
        self.analyze_temporal_patterns()
        self.analyze_article_engagement()
        self.analyze_ecosystem_usage()
        self.calculate_engagement_metrics()

        return self.summary

    def get_recent_events(self, days: int = 7) -> list:
        """Get events from the last N days"""
        dated_events = []
        for e in self.events:
            ts = e.get('TIMESTAMP')
            if ts:
                try:
                    dt = pd.to_datetime(ts)
                    dated_events.append((dt, e))
                except:
                    pass

        if not dated_events:
            return []

        dated_events.sort(key=lambda x: x[0], reverse=True)
        latest = dated_events[0][0]
        cutoff = latest - timedelta(days=days)

        return [e for dt, e in dated_events if dt > cutoff]


def load_events(filepath: str) -> list:
    """Load events from JSON file"""
    with open(filepath, 'r') as f:
        return json.load(f)
