"""The podcast lane publishes its own shard and leaves the fund-letter shards alone."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import podcast_cloud_refresh as refresh


def commands(monkeypatch, *argv):
    seen = []

    def fake_run(cmd):
        seen.append([str(part) for part in cmd])
        return 0

    monkeypatch.setattr(refresh, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['podcast_cloud_refresh.py', *argv])
    assert refresh.main() == 0
    return seen


def scripts(seen):
    return [Path(cmd[1]).name for cmd in seen if len(cmd) > 1]


def test_publish_uses_the_podcast_publisher_not_a_full_insights_rebuild(monkeypatch):
    seen = commands(monkeypatch, '--date', '2026-10-29')
    names = scripts(seen)
    assert 'build_insights.py' not in names
    assert not any('write_insights_shards' in ' '.join(cmd) for cmd in seen)
    publish = names.index('publish_podcast_dashboard.py')
    assert names.index('check_podcast_summary_coverage.py') > publish
    assert not any('--push' in cmd for cmd in seen)


def test_skip_dashboard_publishes_nothing(monkeypatch):
    names = scripts(commands(monkeypatch, '--skip-dashboard'))
    assert 'publish_podcast_dashboard.py' not in names
    assert 'check_podcast_summary_coverage.py' not in names
