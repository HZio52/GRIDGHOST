import argparse,json,os
from pathlib import Path
import httpx

def main():
    p=argparse.ArgumentParser(); p.add_argument('--url',default='http://127.0.0.1:8000')
    p.add_argument('--file',default='data/close_fight_s07.json'); args=p.parse_args()
    body=json.loads(Path(args.file).read_text())
    headers={'X-API-Key':os.getenv('API_KEY','')}
    with httpx.Client(base_url=args.url,timeout=30,headers=headers,trust_env=False) as c:
        r=c.post('/v1/runs',json={'name':Path(args.file).stem}); r.raise_for_status()
        run=r.json()['id']; print('Run:',run)
        for state in body['states']:
            r=c.post(f'/v1/runs/{run}/steps',json=state); r.raise_for_status(); o=r.json()
            print(f"{state['timestamp_s']:>8.1f} | {o['recommendation']:<18} | {o['reason']}")
        r=c.get(f'/v1/runs/{run}/export.csv');r.raise_for_status()
        Path('data/latest_decisions.csv').write_text(r.text)
        print('CSV: data/latest_decisions.csv')
if __name__=='__main__': main()
