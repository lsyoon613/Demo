"""Run three live ASKCOS calls against a local deployment and retain responses."""
import argparse
import json
from pathlib import Path
import time

import requests

from check_backends import askcos_ready


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:9100')
    parser.add_argument('--output', type=Path, default=Path('verified_reports/backend-smoke.json'))
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    for _ in range(120):
        try:
            response = requests.get(base + '/api/admin/get-backend-status', timeout=5)
            response.raise_for_status()
            if askcos_ready(response.json()):
                break
        except requests.RequestException:
            pass
        time.sleep(5)
    else:
        raise RuntimeError('Required ASKCOS models did not become ready')
    reactants = 'CC(C)N1CC(O)C1.Oc1cccc2ccccc12'
    product = 'CC(C)NCC(O)COc1cccc2ccccc12'
    calls = {
        'context': ('/api/context/quarc/call-sync', {'smiles': [reactants + '>>' + product], 'top_k': 3}),
        'forward': ('/api/forward/controller/call-sync', {'backend': 'wldn5', 'model_name': 'pistachio', 'smiles': [reactants], 'reagents': '', 'solvent': ''}),
        'impurity': ('/api/impurity-predictor/call-sync', {'rct_smi': reactants, 'prd_smi': product, 'rea_smi': '', 'sol_smi': '', 'predictor_backend': 'wldn5', 'predictor_model_name': 'pistachio', 'inspector': 'Reaxys inspector', 'topn_outcome': 3, 'insp_threshold': 0.1, 'check_mapping': False}),
    }
    records = {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, (endpoint, payload) in calls.items():
        response = requests.post(base + endpoint, json=payload, timeout=(15, 300))
        response.raise_for_status()
        body = response.json()
        ok = body.get('status_code') == 200 and bool(body.get('result'))
        records[name] = {'url': base + endpoint, 'request': payload, 'response': body, 'ok': ok}
        args.output.write_text(json.dumps(records, indent=2), encoding='utf-8')
        print(f'{name}: {"OK" if ok else "FAILED"}', flush=True)
    if not all(row['ok'] for row in records.values()):
        raise RuntimeError(f'Prediction failed; inspect {args.output}')


if __name__ == '__main__':
    main()
