"""A verified duplicate recording is not a missing published episode."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_podcast_summary_coverage as coverage


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def fixture(root, monkeypatch):
    vault = root/'vault/podcasts'
    monkeypatch.setattr(coverage, 'ROOT', root)
    monkeypatch.setattr(coverage, 'podcasts_root', lambda **kwargs: vault)
    summary = {'status': 'ready', 'source_basis': 'notes', 'overview': 'A sourced episode overview.'}
    canonical = {'episode_id': 'canonical', 'enclosure_hash': 'a'*40, 'reader_summary': summary}
    save(vault/'episodes/show/canonical.meta.json', canonical)
    save(vault/'episodes/show/duplicate.meta.json', {**canonical, 'episode_id': 'duplicate'})
    save(vault/'insights.json', {'episodes': [canonical]})
    save(root/'dashboard/data/insights/podcasts.json', {'podcast_index': [
        {'episode_id': 'canonical', 'summary_preview': 'A sourced episode overview.', 'summary_source_label': 'Show notes'}]})
    save(root/'dashboard/data/insights/podcast_episodes/canonical.json', canonical)
    return vault, canonical


def test_only_verified_unserved_recording_aliases_are_excluded(tmp_path, monkeypatch):
    vault, canonical = fixture(tmp_path, monkeypatch)
    result = coverage.audit()
    assert result['published_missing_count'] == 0
    assert result['deduplicated_aliases'] == {'duplicate': 'canonical'}
    assert result['meta']['with_reader_summary'] == 2
    assert result['catalog']['missing_count'] == 1  # Still visible in source coverage.


@pytest.mark.parametrize('hash_value', ['', 'b'*40, None, 'not-a-recording-hash'])
def test_a_unique_or_unidentified_source_episode_still_blocks_publication(tmp_path, monkeypatch, hash_value):
    vault, canonical = fixture(tmp_path, monkeypatch)
    save(vault/'episodes/show/duplicate.meta.json', {**canonical, 'episode_id': 'duplicate', 'enclosure_hash': hash_value})
    assert coverage.audit()['published_missing'] == ['duplicate']


def test_a_duplicate_that_is_served_still_needs_its_own_index_and_summary(tmp_path, monkeypatch):
    _, canonical = fixture(tmp_path, monkeypatch)
    save(tmp_path/'dashboard/data/insights/podcast_episodes/duplicate.json', {**canonical, 'episode_id': 'duplicate'})
    result = coverage.audit()
    assert result['published_missing'] == ['duplicate']
    assert not result['deduplicated_aliases']


@pytest.mark.parametrize('part', ['index', 'shard'])
def test_the_retained_recording_must_be_fully_published(tmp_path, monkeypatch, part):
    fixture(tmp_path, monkeypatch)
    path = tmp_path/('dashboard/data/insights/podcasts.json' if part == 'index'
                     else 'dashboard/data/insights/podcast_episodes/canonical.json')
    path.unlink()
    assert 'canonical' in coverage.audit()['published_missing']


def test_an_ambiguous_recording_hash_does_not_establish_a_canonical_alias(tmp_path, monkeypatch):
    vault, canonical = fixture(tmp_path, monkeypatch)
    save(vault/'insights.json', {'episodes': [canonical, {**canonical, 'episode_id': 'conflict'}]})
    assert 'duplicate' in coverage.audit()['published_missing']
