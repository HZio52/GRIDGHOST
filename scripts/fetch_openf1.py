"""Run as python -m scripts.fetch_openf1 --help from project root."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from app.openf1 import OpenF1Client,epoch,normalize

def main():
    p=argparse.ArgumentParser(description='Fetch <=5-minute historical window. No private battery data.')
    p.add_argument('--session',type=int,required=True)
    p.add_argument('--own',type=int,required=True)
    p.add_argument('--rival',type=int,required=True)
    p.add_argument('--start',required=True,help='ISO UTC timestamp')
    p.add_argument('--end',required=True,help='ISO UTC timestamp')
    p.add_argument('--energy-mj',type=float,required=True,help='Simulated energy per snapshot')
    p.add_argument('--assume-green',action='store_true',help='Explicit demo assumption, not real flag verification')
    p.add_argument('--output',default='data/openf1_replay.json')
    args=p.parse_args()
    if args.own==args.rival: p.error('Choose distinct drivers')
    if not 0<epoch(args.end)-epoch(args.start)<=300: p.error('Window must be >0 and <=300 seconds')
    if not 0<=args.energy_mj<=4: p.error('Default demo capacity is 4 MJ')
    client=OpenF1Client(); raw={}
    for kind in ('car_data','position','intervals'):
        raw[kind]=[]
        for driver in (args.own,args.rival):
            raw[kind]+=client.fetch(kind,{'session_key':args.session,'driver_number':driver,
                                         'date>=':args.start,'date<=':args.end})
    destination=Path(args.output); destination.parent.mkdir(parents=True,exist_ok=True)
    raw_path=destination.with_name(destination.stem+'_raw.json')
    raw_path.write_text(json.dumps({'source':'https://openf1.org/docs/',
        'fetched_at':datetime.now(timezone.utc).isoformat(),'query':vars(args),'data':raw},indent=2))
    result=normalize(raw,args.own,args.rival,args.energy_mj,args.assume_green)
    if not result['states']:
        raise SystemExit(f'Raw data saved to {raw_path}; no adjacent numeric intervals aligned. '
                         'Choose an actual adjacent-driver fight/window; no fake frames generated.')
    destination.write_text(json.dumps({'states':result['states']},indent=2))
    destination.with_suffix('.metadata.json').write_text(json.dumps(
        {k:v for k,v in result.items() if k!='states'},indent=2))
    print(f"Saved {len(result['states'])} frames to {destination}; raw data: {raw_path}")

if __name__=='__main__': main()
