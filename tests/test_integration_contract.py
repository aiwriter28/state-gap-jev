import json
from pathlib import Path

import pytest
from test_walk import MODEL, ORIGIN, SITE, cli, model_site, site_folder
from walk import (
    attested,
    configured_text,
    load_model,
    merge_retry,
    provenance,
    validate,
)


def test_custom_profile_replaces_commerce_seeds(tmp_path):
    model = {**MODEL, 'profile': {'activities': ['lead'], 'seeds': [{'id': 'expired'}]}}
    loaded = load_model(tmp_path, model_site(tmp_path, model))
    assert 'lead.new.expired' in loaded['cells']
    assert 'lead.new.chargeback' not in loaded['cells']


def test_retry_keeps_both_attempt_costs_and_observations():
    first = {'id': 'a', 'result': 'fail', 'reason': 'done', 'jev_usd': .02, 'jev_calls': 3}
    retry = {'id': 'a', 'result': 'pass', 'reason': 'pass', 'jev_usd': .01, 'jev_calls': 2}
    row = merge_retry(first, retry)
    assert row['result'] == 'flaky'
    assert row['jev_usd'] == .03
    assert row['jev_calls'] == 5
    assert [r['result'] for r in row['attempts']] == ['fail', 'pass']


def test_public_provenance_uses_relative_input_paths(tmp_path):
    site = model_site(tmp_path)
    (tmp_path / 'site.json').write_text(json.dumps(site))
    goals = tmp_path / 'goals.json'
    goals.write_text('[]')
    record = provenance(tmp_path, goals, 'http://localhost:8765', False, 'example', site)
    assert not Path(record['site_dir']).is_absolute()
    assert record['inputs']['model_path'] == 'model.json'
    assert str(tmp_path) not in json.dumps(record)


def test_goal_ids_cannot_escape_the_run_folder():
    goal = {'id': '../outside', 'step': 'pay', 'start': '/', 'goal': 'x', 'pass': {'url': '/'}}
    assert any('id' in problem for problem in validate([goal], SITE))


def test_sandbox_webhook_requires_exact_origin():
    site = {**SITE, 'write': {**SITE['write'], 'sandbox_origin': 'https://sandbox.example.com'}}
    proof = {'payment': {'provider': 'stripe', 'livemode': False, 'account': 'acct_test'},
             'database': {'production': False}, 'auth': {'kind': 'supabase', 'ref': 'abcdefgh'},
             'webhook': 'https://sandbox.example.com.evil.test/webhook'}
    assert any('webhook' in problem for problem in attested(site, proof))


def test_text_helper_never_guesses_an_endpoint_for_a_partial_configuration(monkeypatch):
    monkeypatch.setenv('TEXT_MODEL_API_KEY', 'fixture-secret')
    monkeypatch.delenv('TEXT_MODEL_BASE_URL', raising=False)
    monkeypatch.setenv('TEXT_MODEL', 'chosen-model')
    calls = []
    helper = configured_text(lambda context: calls.append(context) or 'synthetic value')
    with pytest.raises(ValueError, match='Text helper needs'):
        helper({})
    assert calls == []
    monkeypatch.setenv('TEXT_MODEL_BASE_URL', 'https://example.test/v1')
    assert helper({'field': 'name'}) == 'synthetic value'


def test_existing_evidence_cannot_be_overwritten_and_unknown_goal_cannot_pass(tmp_path):
    folder = site_folder(tmp_path, '')
    output = tmp_path / 'evidence'
    output.mkdir()
    (output / 'run.json').write_text('original evidence')
    result = cli(ORIGIN, '--site', str(folder), '--out', str(output), env={'TYPESAFE_API_KEY': 'unused'})
    assert result.returncode != 0
    assert 'already exists' in result.stderr
    assert (output / 'run.json').read_text() == 'original evidence'
    result = cli(ORIGIN, '--site', str(folder), '--only', 'typo', env={'TYPESAFE_API_KEY': 'unused'})
    assert result.returncode != 0 and 'Unknown journey' in result.stderr
