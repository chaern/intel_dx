"""Factory I/O three-color sorting with two numerical vision sensors."""
import time
from collections import Counter
from pymodbus.client import ModbusTcpClient

HOST = '192.168.0.16'
DEVICE_ID = 1
BLUE, GREEN, METAL = {1, 2, 3}, {4, 5, 6}, {7, 8, 9}

def checked(response):
    if response.isError():
        raise RuntimeError(str(response))
    return response

class ColorSorter:
    def __init__(self, host=HOST):
        self.client = ModbusTcpClient(host, port=502, timeout=2, retries=0)
        self.counts = Counter()
        self.events = []
        self.stop_requested = False

    def write(self, address, value):
        checked(self.client.write_coil(address, bool(value), device_id=DEVICE_ID))

    def event(self, text):
        line = time.strftime('%H:%M:%S ') + text
        self.events.append(line)
        print(line, flush=True)

    def stop(self):
        self.stop_requested = True

    def run(self, duration=180):
        if not 0 < duration <= 3600:
            raise ValueError('duration: 1~3600 seconds')
        if not self.client.connect():
            self.client.close()
            raise ConnectionError(HOST)
        self.stop_requested = False
        # Each station has independent blank/rearm detection and pending item.
        stations = [dict(candidate=0, since=0, armed=False, pending=None),
                    dict(candidate=0, since=0, armed=False, pending=None)]
        state, active, moving = 'START', None, False
        since = previous = time.monotonic()
        deadline = since + duration
        try:
            checked(self.client.write_coils(0, [False]*8+[True], device_id=DEVICE_ID))
            self.event('START metal→P0 blue→P1 green→curve')
            while time.monotonic() < deadline and not self.stop_requested:
                now = time.monotonic()
                elapsed, previous = now-previous, now
                bits = checked(self.client.read_discrete_inputs(0,count=6,device_id=DEVICE_ID)).bits
                if state == 'START':
                    if bits[2] and bits[0] and bits[4]:
                        for address in (0,1,2,5,6,7): self.write(address,True)
                        state, moving, since = 'FEED', True, now
                    elif now-since > 5:
                        raise TimeoutError('Run/home signals missing')
                    time.sleep(.02)
                    continue
                if not bits[2] or bits[3]:
                    raise RuntimeError('Simulation stopped/reset')
                codes=checked(self.client.read_input_registers(0,count=2,device_id=DEVICE_ID)).registers
                for i, (s, code) in enumerate(zip(stations,codes)):
                    if code != s['candidate']:
                        s['candidate'],s['since']=code,now
                    if now-s['since'] >= .04:
                        if code == 0:
                            s['armed']=True
                        elif s['armed'] and s['pending'] is None:
                            s['armed']=False
                            if code not in BLUE|GREEN|METAL:
                                raise RuntimeError(f'Unknown vision value {code}')
                            self.event(f'VISION{i} code={code}')
                            if (i==0 and code in METAL) or (i==1 and code in BLUE):
                                s['pending']={'code':code,'travel':0.0}
                            elif i==1 and code in GREEN:
                                self.counts['GREEN']+=1
                                self.event('GREEN → curve')
                            elif i==1 and code in METAL:
                                raise RuntimeError('Metal escaped P0; inspect alignment')
                    if moving and s['pending'] is not None:
                        s['pending']['travel']+=elapsed
                if state == 'FEED':
                    # Downstream priority; travel time advances only while belt moves.
                    ready=[i for i in (1,0) if stations[i]['pending'] is not None and stations[i]['pending']['travel']>=.20]
                    if ready:
                        active=ready[0]
                        self.write(0,False); self.write(2,False)
                        moving=False
                        state,since='SETTLE',now
                elif state=='SETTLE' and now-since>=.10:
                    if not bits[0 if active==0 else 4]:
                        raise RuntimeError('Pusher not home')
                    self.write(3+active,True)
                    state,since='EXTEND',now
                elif state=='EXTEND':
                    if bits[1 if active==0 else 5]:
                        self.event(f'P{active} FRONT_LIMIT')
                        state,since='HOLD',now
                    elif now-since>3: raise TimeoutError(f'P{active} extension')
                elif state=='HOLD' and now-since>=.30:
                    self.write(3+active,False)
                    state,since='RETRACT',now
                elif state=='RETRACT':
                    if bits[0 if active==0 else 4]:
                        color='METAL' if active==0 else 'BLUE'
                        self.counts[color]+=1
                        self.event(f'{color} P{active} BACK_LIMIT confirmed')
                        stations[active]['pending']=None
                        # Keep this sensor disarmed until the pushed item clears.
                        stations[active]['armed']=False
                        self.write(0,True); self.write(2,True)
                        moving=True
                        state,since='CLEAR',now
                    elif now-since>3: raise TimeoutError(f'P{active} retraction')
                elif state=='CLEAR':
                    if codes[active]==0:
                        self.write(0,True); self.write(2,True)
                        moving=True
                        state,since='FEED',now
                    elif now-since>3:
                        raise RuntimeError(f'P{active} vision did not clear')
                time.sleep(.02)
        except KeyboardInterrupt:
            self.event('Interrupted')
        finally:
            try:
                checked(self.client.write_coils(0,[False]*8,device_id=DEVICE_ID))
                self.event(f'STOP {dict(self.counts)} state={state}')
            finally:
                self.client.close()
        return dict(self.counts)

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=float,default=180)
    ColorSorter().run(parser.parse_args().seconds)
