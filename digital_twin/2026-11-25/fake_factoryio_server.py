"""Factory IO 스태커 크레인 씬을 흉내 내는 가짜 Modbus TCP 서버.

주소 맵은 StackerCrane_S_PLAN.md §2.2 와 동일.
외부 라이브러리 없이 표준 라이브러리만으로 Modbus TCP(FC 1,2,3,4,5,6,15,16)를 처리한다.
(pymodbus 3.16의 서버 datastore API가 버전마다 바뀌어서 직접 구현)
실행:  python fake_factoryio_server.py --port 5020 --auto-start
적재할 때마다 랙 상태를 출력한다. Ctrl+C 로 종료.
"""
import argparse
import asyncio
import struct
import time

# ---- 주소 맵 (0-based) ----
DI_SENSOR, DI_MOVX, DI_MOVZ, DI_LEFT, DI_RIGHT, DI_MID, DI_START, DI_RESET = range(8)
CO_LIFT, CO_FL, CO_FR, CO_LOADIN, CO_LOADOUT = 0, 1, 2, 3, 4
CO_CONV0, CO_CONV1, CO_EMIT, CO_REMOVER = 8, 9, 10, 11
HR_TARGET = 0
HOME_POS = 99
FC_DI, FC_CO, FC_HR = 2, 1, 3

COLS, ROWS = 9, 6


class Store:
    """DI / Coil / IR / HR 메모리 (0-based 주소)"""
    def __init__(self, size=64):
        self.mem = {"d": [0] * size, "c": [0] * size, "i": [0] * size, "h": [0] * size}

    @staticmethod
    def area(fc):
        return {1: "c", 5: "c", 15: "c", 2: "d", 3: "h", 6: "h", 16: "h", 4: "i"}[fc]

    def getValues(self, fc, addr, count):
        return self.mem[self.area(fc)][addr:addr + count]

    def setValues(self, fc, addr, values):
        m = self.mem[self.area(fc)]
        for i, v in enumerate(values):
            m[addr + i] = int(v)


def _pack_bits(bits):
    out = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        if b:
            out[i // 8] |= 1 << (i % 8)
    return bytes(out)


def _process(store, fc, body):
    """PDU 처리 → 응답 PDU (bytes)"""
    size = len(store.mem["d"])
    try:
        if fc in (1, 2, 3, 4):
            addr, cnt = struct.unpack(">HH", body[:4])
            if addr + cnt > size:
                return bytes([fc | 0x80, 2])
            vals = store.getValues(fc, addr, cnt)
            if fc in (1, 2):
                data = _pack_bits(vals)
            else:
                data = struct.pack(f">{cnt}H", *vals)
            return bytes([fc, len(data)]) + data
        if fc == 5:
            addr, val = struct.unpack(">HH", body[:4])
            store.setValues(fc, addr, [val == 0xFF00])
            return bytes([fc]) + body[:4]
        if fc == 6:
            addr, val = struct.unpack(">HH", body[:4])
            store.setValues(fc, addr, [val])
            return bytes([fc]) + body[:4]
        if fc == 15:
            addr, cnt, _n = struct.unpack(">HHB", body[:5])
            raw = body[5:]
            bits = [(raw[i // 8] >> (i % 8)) & 1 for i in range(cnt)]
            store.setValues(fc, addr, bits)
            return bytes([fc]) + body[:4]
        if fc == 16:
            addr, cnt, _n = struct.unpack(">HHB", body[:5])
            store.setValues(fc, addr, struct.unpack(f">{cnt}H", body[5:5 + 2 * cnt]))
            return bytes([fc]) + body[:4]
    except (struct.error, IndexError):
        return bytes([fc | 0x80, 3])
    return bytes([fc | 0x80, 1])


async def handle_client(store, reader, writer):
    try:
        while True:
            hdr = await reader.readexactly(7)          # MBAP
            tid, pid, length, uid = struct.unpack(">HHHB", hdr)
            pdu = await reader.readexactly(length - 1)
            resp = _process(store, pdu[0], pdu[1:])
            writer.write(struct.pack(">HHHB", tid, 0, len(resp) + 1, uid) + resp)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        writer.close()


def cell_of(pos):
    """pos -> (z, c)  z:0=아래, c:0=오른쪽"""
    return (pos - 1) // COLS, (pos - 1) % COLS


class Sim:
    def __init__(self, ctx, speed, auto_start):
        self.ctx = ctx
        self.speed = speed
        self.auto_start = auto_start
        self.rack = {}            # pos -> 적재 순번
        self.crane_x, self.crane_z = -1.0, 0.0   # x=-1 : 홈(픽업 위치)
        self.goal = None
        self.target_seen = HOME_POS
        self.fork = 0.0           # -1=왼쪽, 0=중앙, +1=오른쪽
        self.lift = False
        self.carrying = False
        self.boxes = []           # 공급 라인 위 박스 진행도(0..1, 1=센서 위치)
        self.prev_emit = False
        self.errors = []
        self.t0 = time.time()

    # --- datastore 접근 ---
    def co(self, a):
        return bool(self.ctx.getValues(FC_CO, a, 1)[0])

    def set_di(self, a, v):
        self.ctx.setValues(FC_DI, a, [bool(v)])

    def err(self, msg):
        print(f"[SIM ERROR] {msg}")
        self.errors.append(msg)

    def step(self, dt):
        dt *= self.speed
        target = self.ctx.getValues(FC_HR, HR_TARGET, 1)[0]
        if target != self.target_seen:
            self.target_seen = target
            if abs(self.fork) > 0.05:
                self.err(f"포크가 나와 있는 상태에서 이동 지령 {target}")
            if target == HOME_POS:
                self.goal = (-1.0, 0.0)
            elif 1 <= target <= COLS * ROWS:
                z, c = cell_of(target)
                self.goal = (float(c), float(z))
            else:
                self.err(f"잘못된 Target Position {target}")

        # 크레인 이동 (X 3칸/s, Z 2칸/s)
        mov_x = mov_z = False
        if self.goal:
            gx, gz = self.goal
            dx, dz = gx - self.crane_x, gz - self.crane_z
            if abs(dx) > 1e-6:
                self.crane_x += max(-3 * dt, min(3 * dt, dx)); mov_x = True
            if abs(dz) > 1e-6:
                self.crane_z += max(-2 * dt, min(2 * dt, dz)); mov_z = True
            if not (mov_x or mov_z):
                self.goal = None
        self.set_di(DI_MOVX, mov_x)
        self.set_di(DI_MOVZ, mov_z)

        # 포크 (편도 0.8 s)
        fl, fr = self.co(CO_FL), self.co(CO_FR)
        dest = -1.0 if fl and not fr else (1.0 if fr and not fl else 0.0)
        if (fl or fr) and (mov_x or mov_z):
            self.err("이동 중 포크 동작")
        d = dest - self.fork
        self.fork += max(-dt / 0.8, min(dt / 0.8, d))
        self.set_di(DI_LEFT, self.fork <= -0.99)
        self.set_di(DI_RIGHT, self.fork >= 0.99)
        self.set_di(DI_MID, abs(self.fork) < 0.01)

        # 리프트: 픽업 / 내려놓기
        lift = self.co(CO_LIFT)
        at_home = abs(self.crane_x + 1) < 1e-6 and abs(self.crane_z) < 1e-6
        if lift and not self.lift:                      # 상승
            if self.fork <= -0.99 and at_home and self.boxes and self.boxes[0] >= 1.0:
                self.boxes.pop(0); self.carrying = True
            elif not self.carrying:
                self.err("픽업 실패: 포크/위치/물건 조건 불일치")
        if self.lift and not lift and self.carrying:     # 하강
            if self.fork >= 0.99 and not at_home:
                pos = int(round(self.crane_z)) * COLS + int(round(self.crane_x)) + 1
                if pos in self.rack:
                    self.err(f"이미 적재된 칸 {pos}")
                self.rack[pos] = len(self.rack) + 1
                self.carrying = False
                print(f"[SIM] 적재 pos={pos} ({len(self.rack)}개)")
                self.print_rack()
            else:
                self.err("내려놓기 실패: 포크가 랙 쪽이 아님")
        self.lift = lift

        # 공급 라인: Emitter 상승엣지마다 1개
        emit = self.co(CO_EMIT)
        if emit and not self.prev_emit:
            self.boxes.append(0.0)
        self.prev_emit = emit
        conv = self.co(CO_CONV0) and self.co(CO_CONV1)
        for i, b in enumerate(self.boxes):
            limit = 1.0 if i == 0 else min(1.0, self.boxes[i - 1] - 0.3)
            speed = (0.5 if conv else 0) if b < 0.7 else (0.5 if self.co(CO_LOADIN) else 0)
            self.boxes[i] = min(limit, b + speed * dt)
            if self.boxes[i] >= 1.0 and self.co(CO_LOADIN) and i == 0:
                pass  # 센서 끝에서 정지(스토퍼)
        # 실제 씬(At Load)처럼 active-low: 물건 있으면 0
        self.set_di(DI_SENSOR, not (bool(self.boxes) and self.boxes[0] >= 1.0))

        # 자동 Start 버튼: 3초마다 0.5초 눌림 (노트북 접속 시점과 무관하게 동작)
        if self.auto_start:
            t = time.time() - self.t0
            self.set_di(DI_START, (t % 3.0) > 2.5)

    def print_rack(self):
        print("\n랙 상태 (정면, 왼쪽=54쪽):")
        for z in range(ROWS - 1, -1, -1):
            row = ""
            for c in range(COLS - 1, -1, -1):
                row += " #" if (z * COLS + c + 1) in self.rack else " ."
            print(f"z={z} {row}")
        print(f"적재 {len(self.rack)}개, 오류 {len(self.errors)}건")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5020)
    ap.add_argument("--speed", type=float, default=1.0, help="시뮬레이션 배속")
    ap.add_argument("--auto-start", action="store_true", help="2초 뒤 Start 버튼 자동 누름")
    args = ap.parse_args()

    store = Store()
    store.setValues(FC_HR, HR_TARGET, [HOME_POS])
    sim = Sim(store, args.speed, args.auto_start)

    async def loop():
        last = time.time()
        while True:
            await asyncio.sleep(0.01)
            now = time.time()
            sim.step(now - last)
            last = now

    task = asyncio.create_task(loop())
    print(f"가짜 Factory IO 서버: {args.host}:{args.port}")
    server = await asyncio.start_server(lambda r, w: handle_client(store, r, w),
                                        args.host, args.port)
    try:
        async with server:
            await server.serve_forever()
    finally:
        task.cancel()
        sim.print_rack()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
