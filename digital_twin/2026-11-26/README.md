# 2026-11-26 실습 — Lids & Bases 생산 공정 (Production Line)

Factory I/O `Production Line` 씬(머시닝 센터 2대 + 로봇)을 Modbus TCP 서버로 두고, Jupyter(pymodbus 3.x, `device_id`)에서 두 머시닝 센터를 제어해 Lid 와 Base 를 목표 수량(기본 10개)만큼 생산한 뒤 종료합니다.

- [factoryio_lids_bases_modbus.ipynb](factoryio_lids_bases_modbus.ipynb): 제어 노트북 (커널: `Python (cherry venv)`)
- [Production Line.factoryio](Production%20Line.factoryio): Factory I/O 씬 (Driver = Modbus TCP/IP Server 선택 시 기본 매핑 사용)
- [factoryio_sim.py](factoryio_sim.py): Factory I/O 없이 시험하는 가상 Modbus 서버 (`python factoryio_sim.py` → `HOST = "127.0.0.1"`)

## 실행 방법

1. Factory I/O 에서 `Production Line.factoryio` 열기 → `F4` → Driver = **Modbus TCP/IP Server**
2. `F5` (Play) — 하단에 *Modbus TCP/IP Server (Started)* 확인
3. 노트북 `HOST` 를 Driver 화면에 표시된 IP 로 맞추고 셀을 위에서부터 실행
4. 수량 변경: 6번 셀 `TARGET_LIDS`, `TARGET_BASES`

## I/O 맵 (0-based)

| DI | 태그 | Coil | 태그 | Coil | 태그 |
|---|---|---|---|---|---|
| 0 | Lids at entry | 0 | Lids raw conveyor | 7 | Bases raw conveyor |
| 1 | Lids center (busy) | 1 | Lids center (produce lids) | 8 | Bases center (produce lids) |
| 2 | Lids center (has error) | 2 | Lids center (start) | 9 | Bases center (start) |
| 3 | Lids at exit | 3 | Lids center (reset) | 10 | Bases center (reset) |
| 4 | Bases at entry | 4 | Lids center (stop) | 11 | Bases center (stop) |
| 5 | Bases center (busy) | 5 | Lids exit conveyor 1 | 12 | Bases exit conveyor 1 |
| 6 | Bases center (has error) | 6 | Lids exit conveyor 2 | 13 | Bases exit conveyor 2 |
| 7 | Bases at exit | | | 14 | Exit conveyor |
| 8 | FACTORY I/O (Running) | | | | |

Holding Register 0 = Lids counter, 1 = Bases counter

## 장면에서 실측한 동작

- `start` 는 **ON 을 유지**해야 로봇·가공이 진행됨 (끄거나 `stop` ON 이면 일시정지)
- `at entry` / `at exit` 센서는 **Active-Low** (부품이 있으면 0)
- 이미터와 Remover 는 장면에서 자동 동작 (매핑 없음)

## 공정 순서

RUN (raw conveyor·start·exit conveyor ON, exit 센서 감지마다 수량 +1) → 목표 도달 시 FLUSH (start OFF, 출구만 배출) → DONE (두 라인 모두 완료 시 전체 출력 OFF)

## 결과

실제 Factory I/O 에서 Lid 10개, Base 10개 생산 후 자동 종료 (약 325초).
