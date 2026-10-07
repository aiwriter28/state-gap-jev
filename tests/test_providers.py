import providers
import pytest


def test_provider_must_be_explicit_when_both_keys_exist():
    with pytest.raises(ValueError, match='Choose'):
        providers.configure({'TYPESAFE_API_KEY': 'direct', 'OPENROUTER_API_KEY': 'router'})


def test_router_uses_decisions_and_does_not_redirect_text_requests():
    config = providers.configure({'JEV_PROVIDER': 'openrouter', 'OPENROUTER_API_KEY': 'router'})
    calls = []
    def post(url, key, body):
        calls.append((url, key, body))
        return {'model': 'typesafe/jev-1.13-20260917', 'answers': {}, 'usage': {'input_tokens': 100, 'output_tokens': 0, 'cost': .0000042}}
    ledger = []
    wrapped = providers.adapt(post, config, ledger)
    result = wrapped(providers.DIRECT_URL, 'ignored', {'model': 'legacy', 'state': 'x', 'questions': {}})
    assert calls[0][0] == 'https://openrouter.ai/api/alpha/decisions'
    assert calls[0][1] == 'router'
    assert calls[0][2]['model'] == 'typesafe/jev-1.13'
    assert result['model'] == 'typesafe/jev-1.13-20260917'
    assert ledger[0]['cost_usd'] == .0000042
    wrapped('https://helper.example/v1/chat/completions', 'helper', {'model':'text'})
    assert calls[1] == ('https://helper.example/v1/chat/completions', 'helper', {'model':'text'})
    assert len(ledger) == 1


@pytest.mark.parametrize('usage', [{}, {'input_tokens':100}, {'input_tokens':100, 'cost': -1}, {'input_tokens':100,'cost':float('nan')}, {'input_tokens':True,'cost':0}])
def test_unknown_router_spend_is_not_zero(usage):
    with pytest.raises(providers.UsageError):
        providers.normalize({'model':'typesafe/jev-1.13','answers':{},'usage':usage}, 'openrouter')


def test_direct_billing_uses_verified_pinned_model():
    result = providers.normalize({'model':'jev-1.13.0','answers':{},'usage':{'input_tokens':1000000,'output_tokens':0}}, 'typesafe')
    assert result['usage']['cost_usd'] == .042
    with pytest.raises(providers.UsageError):
        providers.normalize({'model':'new-price-model','answers':{},'usage':{'input_tokens':100}}, 'typesafe')


def test_missing_key_does_not_fallback_to_other_provider():
    with pytest.raises(ValueError, match='TYPESAFE_API_KEY'):
        providers.configure({'JEV_PROVIDER':'typesafe','OPENROUTER_API_KEY':'other'})


def test_malformed_key_is_rejected_without_echoing_its_value():
    with pytest.raises(ValueError) as error:
        providers.configure({'JEV_PROVIDER': 'typesafe', 'TYPESAFE_API_KEY': 'private-secret\n'})
    assert 'private-secret' not in str(error.value)
    assert 'whitespace' in str(error.value)
