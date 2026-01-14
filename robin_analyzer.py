"""
Robin Event Analyzer
Comprehensive data analysis for Outside Online user journey insights
Optimized for the specific schema: DOMAIN, TITLE, URL, PATH, TAGS, AUTHORS, etc.
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from urllib.parse import urlparse
from typing import Any

import pandas as pd


def load_events(filepath='robin_complete_events.json'):
    """Load events from JSON file"""
    print(f"Loading events from {filepath}...")
    with open(filepath, 'r') as f:
        events = json.load(f)
    print(f"Loaded {len(events):,} events")
    return events


def parse_stringified_array(value):
    """Parse stringified arrays like '[tag1, tag2]' or '[Name One, Name Two]'"""
    if not value or value == 'null' or value == '[]':
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Try JSON parse first
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except:
            pass
        # Handle format like "[tag1, tag2]"
        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1]
            if inner:
                # Split by comma but be careful with names containing commas
                items = [item.strip() for item in inner.split(',')]
                return [item for item in items if item]
    return []


class RobinAnalyzer:
    """Analyzer for Robin's Outside Online event data"""

    def __init__(self, events: list):
        self.events = events
        self.df = None
        self.summary = {}

    def analyze_publications(self) -> dict:
        """Analyze distribution by publication (DOMAIN field)"""
        print("\n" + "=" * 60)
        print("PUBLICATION ANALYSIS (DOMAIN)")
        print("=" * 60)

        domains = Counter()
        for event in self.events:
            domain = event.get('DOMAIN') or 'unknown'
            domains[domain] += 1

        print(f"\nFound {len(domains)} publications:")
        for domain, count in domains.most_common(30):
            pct = count / len(self.events) * 100
            bar = '█' * int(pct / 2)
            print(f"  {domain:35s} {count:6,} ({pct:5.1f}%) {bar}")

        self.summary['publications'] = dict(domains)
        return dict(domains)

    def extract_tags(self) -> dict:
        """Extract and analyze tags from TAGS field (stringified arrays)"""
        print("\n" + "=" * 60)
        print("TAGS ANALYSIS")
        print("=" * 60)

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

        print(f"\nEvents with tags: {events_with_tags:,} ({events_with_tags/len(self.events)*100:.1f}%)")
        print(f"Unique tags: {len(all_tags)}")

        print(f"\nTop 50 Tags:")
        for tag, count in all_tags.most_common(50):
            print(f"  {tag:50s} {count:5,}")

        self.summary['tags'] = dict(all_tags.most_common(200))
        self.summary['events_with_tags'] = events_with_tags
        return dict(all_tags)

    def analyze_authors(self) -> dict:
        """Analyze authors from AUTHORS field"""
        print("\n" + "=" * 60)
        print("AUTHORS ANALYSIS")
        print("=" * 60)

        authors = Counter()
        for event in self.events:
            authors_raw = event.get('AUTHORS')
            author_list = parse_stringified_array(authors_raw)
            for author in author_list:
                if author and isinstance(author, str):
                    authors[author.strip()] += 1

        print(f"\nUnique authors: {len(authors)}")
        print(f"\nTop 30 most-read authors:")
        for author, count in authors.most_common(30):
            print(f"  {author:40s} {count:5,}")

        self.summary['authors'] = dict(authors.most_common(100))
        return dict(authors)

    def analyze_content_categories(self) -> dict:
        """Extract content categories from URL paths"""
        print("\n" + "=" * 60)
        print("CONTENT CATEGORY ANALYSIS")
        print("=" * 60)

        # Extract first path segment as category
        categories = Counter()
        subcategories = Counter()
        full_paths = Counter()

        for event in self.events:
            path = event.get('PATH', '')
            if path and path.startswith('/'):
                parts = [p for p in path.split('/') if p]
                if parts:
                    # Main category
                    categories[parts[0]] += 1
                    # Subcategory
                    if len(parts) >= 2:
                        subcat = f"{parts[0]}/{parts[1]}"
                        subcategories[subcat] += 1
                    # Full path pattern (remove article slugs)
                    if len(parts) >= 2:
                        path_pattern = '/'.join(parts[:-1]) if len(parts) > 2 else '/'.join(parts[:2])
                        full_paths[path_pattern] += 1

        print(f"\nMain content categories ({len(categories)}):")
        for cat, count in categories.most_common(25):
            pct = count / len(self.events) * 100
            bar = '█' * int(pct / 2)
            print(f"  {cat:35s} {count:6,} ({pct:5.1f}%) {bar}")

        print(f"\nTop subcategories:")
        for subcat, count in subcategories.most_common(30):
            print(f"  {subcat:45s} {count:5,}")

        self.summary['content_categories'] = dict(categories)
        self.summary['subcategories'] = dict(subcategories.most_common(100))
        return {'categories': dict(categories), 'subcategories': dict(subcategories)}

    def analyze_domains_visited(self) -> dict:
        """Analyze actual website domains from URLs"""
        print("\n" + "=" * 60)
        print("WEBSITE DOMAIN ANALYSIS")
        print("=" * 60)

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

        print(f"\nWebsite domains ({len(domains)}):")
        for domain, count in domains.most_common(20):
            pct = count / len(self.events) * 100
            print(f"  {domain:45s} {count:6,} ({pct:5.1f}%)")

        self.summary['website_domains'] = dict(domains)
        return dict(domains)

    def analyze_referrers(self) -> dict:
        """Analyze traffic sources from REFERRER field"""
        print("\n" + "=" * 60)
        print("TRAFFIC SOURCE ANALYSIS")
        print("=" * 60)

        referrers = Counter()
        referrer_domains = Counter()

        for event in self.events:
            referrer = event.get('REFERRER', '')
            if referrer:
                referrers[referrer[:80]] += 1  # Truncate long URLs
                # Extract domain
                if referrer.startswith('http'):
                    try:
                        parsed = urlparse(referrer)
                        domain = parsed.netloc.lower()
                        if domain.startswith('www.'):
                            domain = domain[4:]
                        if domain:
                            referrer_domains[domain] += 1
                    except:
                        pass
            else:
                referrers['(direct/none)'] += 1

        print(f"\nReferrer domains:")
        for domain, count in referrer_domains.most_common(20):
            pct = count / len(self.events) * 100
            print(f"  {domain:45s} {count:6,} ({pct:5.1f}%)")

        # Check for email/newsletter traffic
        email_patterns = ['newsletter', 'email', 'utm_medium=email', 'utm_source=newsletter']
        email_traffic = 0
        for event in self.events:
            url = event.get('URL') or ''
            if url and any(p in url.lower() for p in email_patterns):
                email_traffic += 1

        print(f"\n  Email/Newsletter traffic: {email_traffic:,} ({email_traffic/len(self.events)*100:.1f}%)")

        self.summary['referrer_domains'] = dict(referrer_domains.most_common(50))
        self.summary['email_traffic_count'] = email_traffic
        return {'domains': dict(referrer_domains), 'email_traffic': email_traffic}

    def analyze_temporal_patterns(self) -> dict:
        """Analyze temporal patterns using TIMESTAMP field"""
        print("\n" + "=" * 60)
        print("TEMPORAL ANALYSIS")
        print("=" * 60)

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
            print("  No parseable timestamps found")
            return {}

        timestamps = sorted(timestamps)
        print(f"\nTime range:")
        print(f"  First event: {timestamps[0]}")
        print(f"  Last event:  {timestamps[-1]}")
        print(f"  Duration:    {timestamps[-1] - timestamps[0]}")
        print(f"  Total days:  {(timestamps[-1] - timestamps[0]).days}")

        # Events by hour of day
        hours = Counter([ts.hour for ts in timestamps])
        print(f"\nActivity by hour of day (UTC):")
        max_hour_count = max(hours.values()) if hours else 1
        for hour in range(24):
            count = hours.get(hour, 0)
            bar = '█' * int(count / max_hour_count * 30)
            print(f"  {hour:02d}:00  {count:5,} {bar}")

        # Events by day of week
        days = Counter([ts.day_name() for ts in timestamps])
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        print(f"\nActivity by day of week:")
        max_day_count = max(days.values()) if days else 1
        for day in day_order:
            count = days.get(day, 0)
            bar = '█' * int(count / max_day_count * 30)
            print(f"  {day:10s} {count:5,} {bar}")

        # Events by month
        months = Counter([ts.strftime('%Y-%m') for ts in timestamps])
        print(f"\nActivity by month:")
        max_month_count = max(months.values()) if months else 1
        for month in sorted(months.keys()):
            count = months[month]
            bar = '█' * int(count / max_month_count * 40)
            print(f"  {month}  {count:5,} {bar}")

        # Recent activity
        now = timestamps[-1]
        last_7_days = [ts for ts in timestamps if ts > now - timedelta(days=7)]
        last_30_days = [ts for ts in timestamps if ts > now - timedelta(days=30)]

        print(f"\nRecent activity:")
        print(f"  Last 7 days:  {len(last_7_days):,} events ({len(last_7_days)/7:.1f}/day)")
        print(f"  Last 30 days: {len(last_30_days):,} events ({len(last_30_days)/30:.1f}/day)")

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
        print("\n" + "=" * 60)
        print("ARTICLE ENGAGEMENT ANALYSIS")
        print("=" * 60)

        # Count reads per article
        articles = Counter()
        for event in self.events:
            title = event.get('TITLE')
            url = event.get('URL')
            if title and url:
                articles[(title, url)] += 1

        # Articles read multiple times (high engagement)
        multi_read = [(k, v) for k, v in articles.items() if v > 1]
        single_read = [(k, v) for k, v in articles.items() if v == 1]

        print(f"\nUnique articles/pages viewed: {len(articles):,}")
        print(f"  Read once: {len(single_read):,}")
        print(f"  Read multiple times: {len(multi_read):,}")

        print(f"\nMost re-visited articles:")
        for (title, url), count in sorted(multi_read, key=lambda x: -x[1])[:20]:
            print(f"  [{count}x] {title[:70]}")

        # Identify article types from titles
        how_to = sum(1 for e in self.events if 'how to' in (e.get('TITLE') or '').lower())
        best_of = sum(1 for e in self.events if 'best' in (e.get('TITLE') or '').lower())
        reviews = sum(1 for e in self.events if 'review' in (e.get('TITLE') or '').lower())
        guides = sum(1 for e in self.events if 'guide' in (e.get('TITLE') or '').lower())

        print(f"\nContent type indicators from titles:")
        print(f"  'How to' articles: {how_to:,}")
        print(f"  'Best' lists: {best_of:,}")
        print(f"  Reviews: {reviews:,}")
        print(f"  Guides: {guides:,}")

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

    def calculate_engagement_metrics(self) -> dict:
        """Calculate overall engagement metrics"""
        print("\n" + "=" * 60)
        print("ENGAGEMENT METRICS SUMMARY")
        print("=" * 60)

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

        print(f"\n  Total page views:      {metrics['total_events']:,}")
        print(f"  Tracking period:       {metrics['total_days_tracked']} days")
        print(f"  Avg events/day:        {metrics['events_per_day']:.1f}")
        print(f"  Publications followed: {metrics['unique_publications']}")
        print(f"  Unique tags:           {metrics['unique_tags_encountered']}")
        print(f"  Authors read:          {metrics['unique_authors_read']}")
        print(f"  Unique articles:       {metrics['unique_articles']}")

        self.summary['engagement_metrics'] = metrics
        return metrics

    def generate_insights(self) -> list:
        """Generate key insights from the analysis"""
        print("\n" + "=" * 60)
        print("KEY INSIGHTS")
        print("=" * 60)

        insights = []
        total = len(self.events)

        # Volume insight
        temporal = self.summary.get('temporal', {})
        days = temporal.get('total_days', 1)
        insights.append(f"Robin has {total:,} page views over {days} days (avg {total/days:.1f}/day)")

        # Top publication
        pubs = self.summary.get('publications', {})
        if pubs:
            top_pub = max(pubs.items(), key=lambda x: x[1])
            pct = top_pub[1] / total * 100
            insights.append(f"Top publication: {top_pub[0]} ({pct:.1f}% of all views)")

        # Top categories
        cats = self.summary.get('content_categories', {})
        if cats:
            top_cats = list(cats.items())[:3]
            cat_str = ', '.join([f"{c[0]} ({c[1]})" for c in top_cats])
            insights.append(f"Top content categories: {cat_str}")

        # Interest signals from tags
        tags = self.summary.get('tags', {})
        if tags:
            top_tags = list(tags.items())[:8]
            tag_str = ', '.join([t[0] for t in top_tags])
            insights.append(f"Key interests (tags): {tag_str}")

        # Favorite authors
        authors = self.summary.get('authors', {})
        if authors:
            top_authors = list(authors.items())[:3]
            author_str = ', '.join([a[0] for a in top_authors])
            insights.append(f"Most-read authors: {author_str}")

        # Temporal patterns
        if temporal:
            hours = temporal.get('by_hour', {})
            if hours:
                peak_hour = max(hours.items(), key=lambda x: x[1])[0]
                insights.append(f"Peak reading hour: {peak_hour}:00 UTC")

            days_of_week = temporal.get('by_day_of_week', {})
            if days_of_week:
                peak_day = max(days_of_week.items(), key=lambda x: x[1])[0]
                insights.append(f"Most active day: {peak_day}")

        # Email engagement
        email_traffic = self.summary.get('email_traffic_count', 0)
        if email_traffic:
            pct = email_traffic / total * 100
            insights.append(f"Newsletter engagement: {email_traffic:,} visits from email ({pct:.1f}%)")

        # Re-read content
        article_eng = self.summary.get('article_engagement', {})
        multi_read = article_eng.get('multi_read', 0)
        if multi_read:
            insights.append(f"High engagement: {multi_read} articles read multiple times")

        print()
        for i, insight in enumerate(insights, 1):
            print(f"  {i}. {insight}")

        self.summary['insights'] = insights
        return insights

    def analyze_ecosystem_usage(self) -> dict:
        """Analyze usage across Outside ecosystem (apps, web, watch)"""
        print("\n" + "=" * 60)
        print("ECOSYSTEM USAGE ANALYSIS")
        print("=" * 60)

        ecosystem = {
            'trailforks': {'web': 0, 'app': 0, 'ridelogs': 0, 'map_views': 0, 'photos': 0},
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

            # Parse month for monthly breakdown
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

                # Count specific activities
                if '/ridelog' in path or module == 'ridelog' or content_type == 'ridelog':
                    ecosystem['trailforks']['ridelogs'] += 1
                    # Extract unique ridelog IDs
                    import re
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

            # Editorial sites (VeloNews, Outside Online, Backpacker, Run, etc.)
            else:
                # Count as editorial if it's a known publication or has article content
                editorial_domains = ['velonews', 'outside-online', 'backpacker', 'run',
                                   'trailrunner', 'triathlete', 'ski', 'climbing',
                                   'yogajournal', 'oxygen', 'nationalparktrips', 'www.outsideonline']
                if any(ed in domain for ed in editorial_domains) or domain == 'unknown':
                    ecosystem['editorial']['events'] += 1
                    # Count as article if it has a title
                    if event.get('TITLE'):
                        ecosystem['editorial']['articles'] += 1

        ecosystem['trailforks']['unique_rides'] = len(ridelog_ids)

        # Convert defaultdict to regular dict for JSON serialization
        ecosystem['monthly_app_usage'] = {k: dict(v) for k, v in ecosystem['monthly_app_usage'].items()}

        # Print summary
        tf = ecosystem['trailforks']
        print(f"\nTrailforks Usage:")
        print(f"  Web events: {tf['web']:,}")
        print(f"  App events: {tf['app']:,}")
        print(f"  Ride logs viewed: {tf['ridelogs']} ({tf['unique_rides']} unique rides)")
        print(f"  Map views: {tf['map_views']}")
        print(f"  Photos: {tf['photos']}")

        print(f"\nOther Platforms:")
        print(f"  Editorial Sites: {ecosystem['editorial']['events']:,} events ({ecosystem['editorial']['articles']:,} articles)")
        print(f"  Gaia GPS: {ecosystem['gaia_gps']['events']} events")
        print(f"  Outside App: {ecosystem['outside_app']['events']} events")
        print(f"  Outside Watch: {ecosystem['outside_watch']['events']} events")
        print(f"  Devices: {ecosystem['devices']['events']} events")

        self.summary['ecosystem'] = ecosystem
        return ecosystem

    def run_full_analysis(self) -> dict:
        """Run complete analysis pipeline"""
        print("\n" + "=" * 60)
        print(f"ROBIN EVENT ANALYSIS - {len(self.events):,} EVENTS")
        print("Outside Online User Journey Analysis")
        print("=" * 60)

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
        self.generate_insights()

        return self.summary

    def save_summary(self, filepath='robin_summary.json'):
        """Save summary to JSON file"""
        print(f"\nSaving summary to {filepath}...")
        with open(filepath, 'w') as f:
            json.dump(self.summary, f, indent=2, default=str)
        file_size = os.path.getsize(filepath)
        print(f"Summary saved ({file_size / 1024:.1f} KB)")


def main():
    # Load events
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'robin_complete_events.json'

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Run kafka_consumer.py first.")
        sys.exit(1)

    events = load_events(input_file)

    # Run analysis
    analyzer = RobinAnalyzer(events)
    summary = analyzer.run_full_analysis()

    # Save outputs
    analyzer.save_summary('robin_summary.json')

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"\nOutput files:")
    print(f"  - robin_complete_events.json ({os.path.getsize('robin_complete_events.json')/1024/1024:.1f} MB)")
    print(f"  - robin_summary.json (statistics & insights)")


if __name__ == "__main__":
    main()
