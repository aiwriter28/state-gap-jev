"""Make one small, billable synthetic Jev request using the selected provider."""
import json
import math
import sys
import urllib.error
import urllib.request

from providers import configure, normalize


def main():
    config = configure()
    body = {'model': config['model'], 'state': 'An existing customer needs five additional service hours.',
            'questions': {'route': {'type': 'choice', 'instructions': 'Choose the relevant customer action.',
                                   'criteria': {'add_hours': 'Add service time to an existing agreement.',
                                                'new_contract': 'Start the first service agreement.'}}}}
    request = urllib.request.Request(config['url'], data=json.dumps(body).encode(), method='POST',
                                     headers={'Authorization': 'Bearer ' + config['key'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = normalize(json.load(response), config['provider'])
    answer = result['answers'].get('route', {})
    probabilities = answer.get('probabilities', {})
    def valid_number(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
    if (answer.get('type') != 'choice' or set(probabilities) != {'add_hours', 'new_contract'}
            or not all(valid_number(v) for v in probabilities.values())
            or abs(sum(probabilities.values()) - 1) > .02 or not valid_number(answer.get('confidence'))
            or answer.get('choice') != 'add_hours' or probabilities['add_hours'] < probabilities['new_contract']):
        raise ValueError('Provider answered, but the synthetic decision contract did not pass.')
    print(json.dumps({'provider': config['provider'], 'model': result['model'], 'choice': answer['choice'],
                      'confidence': answer['confidence'], 'usage': result['usage'], 'check': 'synthetic API contract only'}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as exc:
        print(f'Provider HTTP {exc.code}. Check credentials, credits, model and endpoint.', file=sys.stderr)
        sys.exit(1)
    except (ValueError, urllib.error.URLError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
