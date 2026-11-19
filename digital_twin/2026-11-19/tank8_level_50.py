import time
from pathlib import Path
from pymodbus.client import ModbusTcpClient

stop_file = Path(__file__).with_name('tank8.stop')
c = ModbusTcpClient('192.168.0.226', port=502, timeout=2, retries=0)

def check(r):
    if r.isError():
        raise RuntimeError(str(r))
    return r

if not c.connect():
    raise ConnectionError('Factory I/O connection failed')
integral = 500.0
previous_time = time.monotonic()
last_log = 0
deadline = time.monotonic() + 60
stable_since = None
achieved = False
try:
    check(c.write_register(17, 0, device_id=1))
    while not stop_file.exists() and time.monotonic() < deadline:
        now = time.monotonic()
        dt = min(now - previous_time, 1.0)
        previous_time = now
        level = check(c.read_input_registers(16, count=1, device_id=1)).registers[0]
        if not 0 <= level <= 1000:
            raise ValueError(f'Invalid level: {level}')
        error = 500 - level
        if abs(error) <= 5:
            stable_since = stable_since or now
            if now - stable_since >= 2:
                achieved = True
                print(f'Target reached: {level / 10:.1f}%', flush=True)
                break
        else:
            stable_since = None
        candidate = integral + 1.5 * error * dt
        raw = 4 * error + candidate
        if 0 <= raw <= 1000 or (raw > 1000 and error < 0) or (raw < 0 and error > 0):
            integral = max(0.0, min(1000.0, candidate))
        command = round(max(0, min(1000, 4 * error + integral)))
        check(c.write_register(16, command, device_id=1))
        if now - last_log >= 2:
            print(f'level={level / 10:.1f}% fill={command / 10:.1f}% target=50.0%', flush=True)
            last_log = now
        time.sleep(0.2)
    if not achieved:
        print('Time limit reached before stable target.', flush=True)
finally:
    try:
        check(c.write_registers(16, [0, 0], device_id=1))
        print('Controller stopped; both valves closed.', flush=True)
    finally:
        c.close()
