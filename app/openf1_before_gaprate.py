"""Historical data adapter. Never infers battery, flags, or arbitrary pair gaps."""
import bisect
from datetime import datetime
import math
import time
import httpx
from .schemas import State

BASE_URL = 'https://api.openf1.org/v1'
ENDPOINTS = {'sessions','car_data','intervals','position','race_control','laps','weather','stints'}

def epoch(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None: raise ValueError('Use timezone-aware ISO timestamps')
    return result.timestamp()

class OpenF1Client:
    def __init__(self, transport=None):
        self.transport=transport
        self.last_request=0.
    def fetch(self, endpoint, params):
        if endpoint not in ENDPOINTS: raise ValueError('Endpoint not allowed')
        with httpx.Client(base_url=BASE_URL+'/',timeout=30,transport=self.transport) as client:
            for attempt in range(3):
                # Conservative pacing: <30 calls/minute including retries.
                time.sleep(max(0., 2.1-(time.monotonic()-self.last_request)))
                self.last_request=time.monotonic()
                response=client.get(endpoint,params=params)
                if response.status_code in (429,500,502,503,504) and attempt < 2:
                    try: delay=float(response.headers.get('Retry-After',2**attempt))
                    except ValueError: delay=2**attempt
                    time.sleep(min(30,max(0,delay)))
                    continue
                response.raise_for_status()
                data=response.json()
                if not isinstance(data,list) or any(not isinstance(r,dict) for r in data):
                    raise ValueError('Expected a JSON array of objects')
                if len(data)>50000: raise ValueError('Too many records; reduce requested time window')
                return data
        raise RuntimeError('Request failed')

class Series:
    def __init__(self, rows):
        self.rows=sorted(rows,key=lambda r:epoch(r['date']))
        self.times=[epoch(r['date']) for r in self.rows]
    def before(self,t):
        index=bisect.bisect_right(self.times,t)-1
        return None if index < 0 else (self.rows[index],t-self.times[index])

def normalize(raw, own, rival, energy_mj, assume_green=False):
    """Only joins previous observations. Keeps numeric adjacent-driver intervals.
    Energy is a user-selected simulated snapshot at each frame, not recorded telemetry.
    """
    if own == rival: raise ValueError('Choose two distinct drivers')
    streams={}
    for kind in ('car_data','position','intervals'):
        for driver in (own,rival):
            streams[kind,driver]=Series([r for r in raw[kind] if r.get('driver_number')==driver])
    own_rows=streams['car_data',own].rows
    states=[]; skipped=0; last_t=-math.inf
    for row in own_rows:
        t=epoch(row['date'])
        if t-last_t<1.: continue  # Avoid repeatedly treating 3.7Hz samples as independent evidence.
        last_t=t
        rv=streams['car_data',rival].before(t)
        op=streams['position',own].before(t)
        rp=streams['position',rival].before(t)
        if not all((rv,op,rp)):
            skipped+=1; continue
        delta=op[0].get('position',0)-rp[0].get('position',0)
        if abs(delta)!=1:
            skipped+=1; continue
        behind=own if delta==1 else rival
        interval=streams['intervals',behind].before(t)
        if interval is None:
            skipped+=1; continue
        value=interval[0].get('interval')
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 0<=value<=30:
            skipped+=1; continue
        if row.get('speed') is None or rv[0].get('speed') is None:
            skipped+=1; continue
        age=max(rv[1],op[1],rp[1],interval[1])
        # Repeated position values can age; conservative freshness may abstain until refreshed.
        state=State(timestamp_s=t,own_speed_kph=row['speed'],rival_speed_kph=rv[0]['speed'],
                    gap_s=value if delta==1 else -value,own_energy_mj=energy_mj,
                    data_age_s=min(age,86400),track_status='GREEN' if assume_green else 'UNKNOWN',
                    speed_source='openf1',gap_source='openf1_adjacent_interval',
                    energy_source='simulated',status_source='user_supplied')
        states.append(state.model_dump())
    return {'states':states,'skipped_frames':skipped,
            'notes':['Energy is a fixed simulated snapshot at each frame.',
                     'Track status is UNKNOWN unless explicitly assumed GREEN for a demo.',
                     'Only adjacent-driver intervals are used; no future observations are joined.',
                     'Historical observations do not change in response to recommendations.']}
