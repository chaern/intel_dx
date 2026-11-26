"""
가상 Factory I/O - "Production Line" (Lids & Bases) 장면 시뮬레이터 (Modbus TCP 서버)

실제 Factory I/O 가 없을 때 노트북(factoryio_lids_bases_modbus.ipynb)을 시험하기 위한
간단한 물리 모델입니다. I/O 주소는 노트북의 주소 맵과 같습니다.

실행:
    python factoryio_sim.py                 # 127.0.0.1:502 에서 서버 시작
    python factoryio_sim.py --port 5020     # 포트 변경
    python factoryio_sim.py --speed 3       # 시뮬레이션 3배속

노트북에서는 HOST = "127.0.0.1" (그리고 바꿨다면 PORT) 로 바꾸고 실행하세요.

모델 (라인마다 동일, Lids center / Bases center):
  Emitter(자동) --> [raw conveyor] --(entry 센서, 끝단 스토퍼)--> 머시닝센터(로봇)
          --> [exit conveyor 1,2] --(exit 센서)--> [공용 Exit conveyor] --> Remover(자동)
  - start 코일이 ON 인 동안만 로봇/가공이 진행되고, stop 이 ON 이면 일시정지 (실제 장면과 동일)
  - entry/exit 센서는 Active-Low (부품이 있으면 0)
"""
import argparse
import asyncio
import time

import struct

# ---------------- I/O 주소 (노트북과 동일) ----------------
LINES = {
    "LID": dict(
        di_entry=0, di_busy=1, di_error=2, di_exit=3,
        co_raw=0, co_produce=1, co_start=2, co_reset=3, co_stop=4,
        out_conv=[5, 6], hr_display=0, machining_time=10.0),
    "BASE": dict(
        di_entry=4, di_busy=5, di_error=6, di_exit=7,
        co_raw=7, co_produce=8, co_start=9, co_reset=10, co_stop=11,
        out_conv=[12, 13], hr_display=1, machining_time=12.0),
}
CO_EXIT_CONV = 14      # 공용 Exit conveyor
DI_RUNNING = 8         # FACTORY I/O (Running)
MAX_QUEUE = 3          # raw conveyor 위 최대 대기 부품 수

CONV_SPEED = 1.0       # m/s
CONV_LEN = 6.0         # m
PART_GAP = 0.6         # m (부품 간 최소 간격)
EMIT_INTERVAL = 1.5    # s (Emit 유지 시 투입 간격)
ROBOT_LOAD = 1.5       # s (로봇이 원자재를 집어 넣는 시간)
ROBOT_UNLOAD = 1.5     # s (가공품을 꺼내 출구 컨베이어에 놓는 시간)
EXIT_SENSOR = (4.5, 5.5)

# ---------------- Modbus 메모리 (0-based) ----------------
MEM = {"co": [False] * 64, "di": [False] * 64, "hr": [0] * 64, "ir": [0] * 64}


def _pack_bits(bits):
    out = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        if b:
            out[i // 8] |= 1 << (i % 8)
    return bytes(out)


def _handle_pdu(pdu):
    """Modbus PDU 처리 (FC 1,2,3,4,5,6,15,16). 응답 PDU 반환."""
    fc = pdu[0]
    try:
        if fc in (1, 2, 3, 4):
            addr, cnt = struct.unpack(">HH", pdu[1:5])
            area = {1: "co", 2: "di", 3: "hr", 4: "ir"}[fc]
            vals = MEM[area][addr:addr + cnt]
            if len(vals) != cnt:
                raise IndexError
            if fc in (1, 2):
                data = _pack_bits(vals)
            else:
                data = b"".join(struct.pack(">H", int(v) & 0xFFFF) for v in vals)
            return bytes([fc, len(data)]) + data
        if fc == 5:
            addr, val = struct.unpack(">HH", pdu[1:5])
            MEM["co"][addr] = val == 0xFF00
            return pdu[:5]
        if fc == 6:
            addr, val = struct.unpack(">HH", pdu[1:5])
            MEM["hr"][addr] = val
            return pdu[:5]
        if fc == 15:
            addr, cnt, _n = struct.unpack(">HHB", pdu[1:6])
            raw = pdu[6:]
            for i in range(cnt):
                MEM["co"][addr + i] = bool(raw[i // 8] >> (i % 8) & 1)
            return pdu[:5]
        if fc == 16:
            addr, cnt, _n = struct.unpack(">HHB", pdu[1:6])
            for i in range(cnt):
                MEM["hr"][addr + i] = struct.unpack(">H", pdu[6 + 2 * i:8 + 2 * i])[0]
            return pdu[:5]
        return bytes([fc | 0x80, 1])          # Illegal function
    except (IndexError, struct.error):
        return bytes([fc | 0x80, 2])          # Illegal data address


async def handle_client(reader, writer):
    peer = writer.get_extra_info("peername")
    print(f"클라이언트 접속: {peer}")
    try:
        while True:
            header = await reader.readexactly(7)          # MBAP 헤더
            tid, pid, length, uid = struct.unpack(">HHHB", header)
            pdu = await reader.readexactly(length - 1)
            resp = _handle_pdu(pdu)
            writer.write(struct.pack(">HHHB", tid, pid, len(resp) + 1, uid) + resp)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        print(f"클라이언트 종료: {peer}")
        writer.close()


class Line:
    def __init__(self, name, cfg):
        self.name, self.cfg = name, cfg
        self.in_parts = []        # 입구 컨베이어 위 부품 위치(m)
        self.out_parts = []       # 출구 컨베이어 위 부품 위치(m)
        self.phase = "IDLE"       # IDLE / LOAD / MACHINING / UNLOAD
        self.t = 0.0              # 현재 phase 경과시간
        self.last_emit = -99.0
        self.removed = 0
        self.display = None

    def update(self, co, dt, now):
        c = self.cfg
        # ---- Emitter (장면에서 자동 동작) ----
        if now - self.last_emit >= EMIT_INTERVAL and len(self.in_parts) < MAX_QUEUE:
            if not self.in_parts or min(self.in_parts) > PART_GAP:
                self.in_parts.append(0.0)
                self.last_emit = now
                print(f"[{self.name}] Emitter: 원자재 투입 (입구 컨베이어 {len(self.in_parts)}개)")

        # ---- 입구 컨베이어 (끝단 스토퍼에서 정지, 부품끼리 겹치지 않음) ----
        if co[c["co_raw"]]:
            self.in_parts.sort(reverse=True)
            limit = CONV_LEN
            for i, p in enumerate(self.in_parts):
                self.in_parts[i] = min(p + CONV_SPEED * dt, limit)
                limit = self.in_parts[i] - PART_GAP

        entry = any(p >= CONV_LEN - 0.2 for p in self.in_parts)

        # ---- 머시닝센터 + 로봇 ----
        stopped = co[c["co_stop"]] or not co[c["co_start"]]   # start 를 유지해야 진행
        if co[c["co_reset"]] and self.phase != "IDLE":
            print(f"[{self.name}] Reset")
            self.phase, self.t = "IDLE", 0.0
        if not stopped:
            self.t += dt
            if self.phase == "IDLE" and entry:
                self.in_parts.remove(max(self.in_parts))
                self.phase, self.t = "LOAD", 0.0
                print(f"[{self.name}] 로봇 로딩 시작")
            elif self.phase == "LOAD" and self.t >= ROBOT_LOAD:
                self.phase, self.t = "MACHINING", 0.0
            elif self.phase == "MACHINING" and self.t >= c["machining_time"]:
                self.phase, self.t = "UNLOAD", 0.0
            elif self.phase == "UNLOAD" and self.t >= ROBOT_UNLOAD:
                if not self.out_parts or min(self.out_parts) > PART_GAP:
                    self.out_parts.append(0.0)
                    self.phase, self.t = "IDLE", 0.0
                    print(f"[{self.name}] 가공 완료 -> 출구 컨베이어")

        busy = self.phase != "IDLE"

        # ---- 출구 컨베이어 -> 공용 Exit conveyor -> Remover(자동) ----
        if all(co[a] for a in c["out_conv"]):
            self.out_parts = [p + CONV_SPEED * dt for p in self.out_parts]
        if co[CO_EXIT_CONV]:                  # 끝에 도달한 부품은 공용 컨베이어로 넘어가 Remover 가 제거
            n = len(self.out_parts)
            self.out_parts = [p for p in self.out_parts if p < CONV_LEN]
            if len(self.out_parts) < n:
                self.removed += n - len(self.out_parts)
                print(f"[{self.name}] Remover: 제거 누계 {self.removed}")
        self.out_parts = [min(p, CONV_LEN) for p in self.out_parts]
        exit_ = any(EXIT_SENSOR[0] <= p <= EXIT_SENSOR[1] for p in self.out_parts)

        return {
            c["di_busy"]: busy, c["di_error"]: False,
            c["di_entry"]: not entry, c["di_exit"]: not exit_,     # Active-Low
        }


async def physics(lines, speed):
    prev = time.time()
    sim_t = 0.0
    while True:
        await asyncio.sleep(0.02)
        now = time.time()
        dt = (now - prev) * speed
        prev = now
        sim_t += dt
        co = MEM["co"]
        di = [False] * 16
        di[DI_RUNNING] = True
        for ln in lines:
            for a, v in ln.update(co, dt, sim_t).items():
                di[a] = v
        MEM["di"][:16] = di
        hr = MEM["hr"]
        for ln in lines:
            v = hr[ln.cfg["hr_display"]]
            if v != ln.display:
                ln.display = v
                print(f"[{ln.name}] Counter = {v}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args()

    lines = [Line(n, c) for n, c in LINES.items()]
    print(f"가상 Factory I/O 시작: {args.host}:{args.port} (모든 device_id 응답, {args.speed}배속)")
    asyncio.create_task(physics(lines, args.speed))
    server = await asyncio.start_server(handle_client, args.host, args.port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("시뮬레이터 종료")
