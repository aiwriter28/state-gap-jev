"""Jev transport selection. Provider contracts verified against official docs on 2026-10-07."""
import math
import os

DIRECT_URL = 'https://api.typesafe.ai/v1/systemone'
ROUTER_URL = 'https://openrouter.ai/api/alpha/decisions'
DIRECT_MODEL = 'jev-1.13.0'
ROUTER_MODEL = 'typesafe/jev-1.13'


class UsageError(ValueError):
    """A decision's billed usage cannot be accounted for safely."""


def configure(env=None):
    env = os.environ if env is None else env
    provider = env.get('JEV_PROVIDER')
    if not provider:
        available = [p for p, key in [('typesafe', 'TYPESAFE_API_KEY'), ('openrouter', 'OPENROUTER_API_KEY')] if env.get(key)]
        if len(available) != 1:
            raise ValueError('Choose JEV_PROVIDER=typesafe or openrouter and configure its API key locally.')
        provider = available[0]
    if provider not in ('typesafe', 'openrouter'):
        raise ValueError('JEV_PROVIDER must be typesafe or openrouter.')
    key_name = 'TYPESAFE_API_KEY' if provider == 'typesafe' else 'OPENROUTER_API_KEY'
    if not env.get(key_name):
        raise ValueError(f'Set {key_name} in your local environment. Never paste it into chat.')
    key = env[key_name]
    if not isinstance(key, str) or not key.isascii() or any(character.isspace() for character in key):
        raise ValueError(f'{key_name} must be ASCII without whitespace. Check the local credential value.')
    return {'provider': provider, 'key': key,
            'url': DIRECT_URL if provider == 'typesafe' else ROUTER_URL,
            'model': DIRECT_MODEL if provider == 'typesafe' else ROUTER_MODEL}


def normalize(result, provider):
    if not isinstance(result, dict) or not isinstance(result.get('answers'), dict) or not isinstance(result.get('model'), str):
        raise UsageError('Jev returned an invalid decision envelope. Stop and inspect provider compatibility.')
    usage = result.get('usage')
    if not isinstance(usage, dict) or type(usage.get('input_tokens')) is not int or usage['input_tokens'] < 0:
        raise UsageError('Jev usage is missing or invalid; spend is unknown. Stop before another journey.')
    if provider == 'typesafe':
        if result['model'] != DIRECT_MODEL:
            raise UsageError('TypeSafe returned an unpriced model. Verify its price before continuing.')
        cost = usage['input_tokens'] * .042 / 1_000_000
    else:
        cost = usage.get('cost')
    if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
        raise UsageError('Jev cost is missing or invalid; spend is unknown. Stop before another journey.')
    return {**result, 'usage': {**usage, 'cost_usd': cost}}


def adapt(post, config, ledger):
    """Redirect only the pinned upstream Jev endpoint. Text-helper transport stays separate."""
    def call(url, key, body):
        if url != DIRECT_URL:
            return post(url, key, body)
        entry = {'provider': config['provider'], 'model': config['model'], 'cost_usd': None}
        ledger.append(entry)  # A failed request may have reached the provider; never count it as free.
        result = normalize(post(config['url'], config['key'], {**body, 'model': config['model']}), config['provider'])
        entry.update({'model': result['model'], **result['usage']})
        return result
    return call
