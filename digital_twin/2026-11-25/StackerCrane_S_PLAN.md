# 스태커 크레인 S자 적재 제어 — 구현 계획서

> 대상: 이 문서만 보고 구현하는 코딩 에이전트.
> 원칙: **문서에 적힌 값·순서를 그대로 따른다.** 애매하면 임의로 바꾸지 말고 `⚠ 확인 필요` 항목을 그대로 두고 사용자에게 보고한다.

---

## 0. 산출물

| 파일 | 내용 |
|---|---|
| `StackerCrane_S.ipynb` | 실제 제어 노트북 (Factory IO에 접속) |
| `fake_factoryio_server.py` | Factory IO 없이 로직을 시험하는 가짜 Modbus 서버(시뮬레이터) |
| `StackerCrane_S_PLAN.md` | 이 문서 |

---

## 1. 환경

| 항목 | 값 |
|---|---|
| Python | `C:\cherry\venv` (Python 3.13) |
| 라이브러리 | **pymodbus 3.x, 3.10 이상** (설치본 3.16.2). 모든 호출에 `device_id=` 키워드 사용. `slave=`/`unit=` **사용 금지**(구버전 이름) |
| 통신 | Modbus TCP. **Factory IO = 서버**, 노트북(Python) = 클라이언트 |
| 서버 주소 | 기본 `192.168.0.16:502`, `device_id=1` (기존 노트북과 동일). 같은 PC면 `127.0.0.1` |
| 실행 | `jupyter_start.bat` → 브라우저에서 `http://127.0.0.1:8888` |

### 1.1 pymodbus 3.x 호출 형식 (그대로 사용)

```python
from pymodbus.client import ModbusTcpClient
client = ModbusTcpClient(HOST, port=PORT, timeout=3)
client.connect()                                         # True/False 반환
rr = client.read_discrete_inputs(0, count=8, device_id=1)  # rr.bits[0..7]
client.write_coil(0, True, device_id=1)
client.write_register(0, 15, device_id=1)
rr.isError()                                             # 모든 응답에 대해 확인
client.close()
```

- `count`는 **키워드 전용**이다. `read_discrete_inputs(0, 8)` 처럼 쓰면 에러.
- `rr.bits`는 8의 배수 길이로 패딩되므로 **필요한 개수만 슬라이스**해서 쓴다.

---

## 2. Factory IO 쪽 구현 (씬 + 드라이버)

### 2.1 씬 (구현 완료 — 기본 제공 "Automated Warehouse" 씬 사용)
- `Welcome(☰) > Scenes > Automated Warehouse` 를 연다. 랙 9×6, 스태커 크레인, Entry/Load/Unload/Exit 컨베이어, Emitter, Remover, 컨트롤 박스가 이미 배치돼 있다.
- 편집 후 `File > Save As` 로 `My Scenes`에 저장(예: `stacker_S`). 원본 씬은 덮어쓰지 않는다.
- 실측으로 확인된 씬 특성 (**코드에 반영됨**):

| 항목 | 실측 결과 | 코드 반영 |
|---|---|---|
| 위치 번호 | 9 = 맨 아래 왼쪽, 10 = 2번째 행 맨 오른쪽 → `pos = z*9 + c + 1` (지그재그 아님) | `pos_from_cell()` 그대로 |
| 정위치 | `Target Position = 99` → Load 컨베이어 앞으로 복귀 | `HOME_POS = 99` |
| 포크 | `Forks Left` = Load 컨베이어(픽업) 쪽, `Forks Right` = 랙 쪽 | `FORK_PICK_SIDE='ForkLeft'` |
| Sensor(At Load) | 반사형 센서 → **물건 있으면 0, 없으면 1 (active-low)** | `SENSOR_ACTIVE_LOW = True` |
| Emitter | 씬 설정상 **코일과 무관하게 자동 배출**(드라이버 화면에 `!` 표시) | 펄스는 그대로 두되 영향 없음 |
| Load in | 센서 감지 후에도 계속 돌리면 팔레트가 컨베이어 끝에서 **떨어짐** | 감지 즉시 OFF |
| Conveyor0(Entry) | 계속 ON이면 뒤 팔레트가 밀려와 **크레인에 걸려 이동 불가(MovingX 계속 1)** | `STOP_FEED_ON_SENSOR = True`: 감지 시 Conveyor0도 OFF, 다음 사이클 [1]에서 ON |

### 2.2 드라이버 설정 (F4 — 구현 완료)
1. 드라이버: **Modbus TCP/IP Server**, Host `192.168.0.16`(이 PC), Port `502`, Slave ID `1`, **Auto start 체크**.
2. I/O Points: Digital Inputs `0 / 8`, Digital Outputs(Coils) `0 / 12`, Register Outputs(Holding) `0 / 1`.
3. `CLEAR` 후 아래처럼 태그를 슬롯에 드래그:

| 영역 | Modbus 번호 | pymodbus 주소 | 사양 이름 | 씬 태그 |
|---|---|---|---|---|
| Discrete Input | 10001 | 0 | Sensor | At Load |
| Discrete Input | 10002 | 1 | MovingX | Moving X |
| Discrete Input | 10003 | 2 | MovingZ | Moving Z |
| Discrete Input | 10004 | 3 | Left Limit | At Left |
| Discrete Input | 10005 | 4 | Right Limit | At Right |
| Discrete Input | 10006 | 5 | Middle Limit | At Middle |
| Discrete Input | 10007 | 6 | Start Button 0 | Start |
| Discrete Input | 10008 | 7 | Reset Button 0 | Reset |
| Coil | 00001 | 0 | Lift | Lift |
| Coil | 00002 | 1 | Fork Left | Forks Left |
| Coil | 00003 | 2 | Fork Right | Forks Right |
| Coil | 00004 | 3 | Load in | Load Conveyor |
| Coil | 00005 | 4 | Load out | Unload Conveyor |
| Coil | 00006~00008 | 5~7 | (미사용) | — |
| Coil | 00009 | 8 | Conveyor0 | Entry Conveyor |
| Coil | 00010 | 9 | Conveyor1 | Exit Conveyor |
| Coil | 00011 | 10 | Emitter 0 | Emitter |
| Coil | 00012 | 11 | Remover 0 | Remover |
| Holding Register | 40001 | 0 | Target Position | Target Position |

> 변환 규칙: `pymodbus 주소 = Modbus 번호 − 영역 시작번호` (10001→0, 00001→0, 40001→0).

4. 드라이버 화면 상단에 초록 체크(서버 동작) 확인 후 씬을 **Play(F5)**. 씬이 멈춰 있으면 값이 바뀌지 않는다.
5. 실행 중 꼬이면 툴바의 **Reset(↻)** 으로 씬을 초기화한다(물건 제거, 크레인 원위치).

### 2.3 Factory IO 없이 시험하기
`fake_factoryio_server.py`가 위와 **같은 주소 맵**으로 크레인·컨베이어·센서를 흉내 낸다.
- 표준 라이브러리만으로 Modbus TCP 서버를 직접 구현(pymodbus 3.16의 서버 datastore API는 deprecated이고 버전마다 바뀌므로 사용하지 않음).
- `--auto-start`: Start 버튼을 3초마다 0.5초씩 눌러 준다. `--speed 5`: 5배속.
- 잘못된 동작(포크가 나온 채 이동 지령, 빈 포크로 픽업, 같은 칸 중복 적재 등)은 `[SIM ERROR]`로 출력된다.

```powershell
C:\cherry\venv\Scripts\python.exe fake_factoryio_server.py --port 5020 --auto-start
```
노트북 설정 셀에서 `HOST='127.0.0.1'`, `PORT=5020`으로 바꿔 실행하면 된다. 종료 시 서버가 랙 상태를 ASCII로 출력한다.

---

## 3. 랙 좌표와 S자 패턴

### 3.1 Target Position 번호 규칙
- 랙: 가로(X) 9칸, 세로(Z) 6칸. **우측 아래 = 1, 좌측 위 = 54.**
- 번호는 **아래 행부터, 각 행은 오른쪽 → 왼쪽**으로 증가한다고 가정:

```
pos = z * 9 + c + 1
  z : 0(맨 아래) ~ 5(맨 위)
  c : 0(맨 오른쪽) ~ 8(맨 왼쪽)
```

```
        왼쪽                                  오른쪽
z=5 |  54  53  52  51  50  49  48  47  46 |
z=4 |  45  44  43  42  41  40  39  38  37 |
z=3 |  36  35  34  33  32  31  30  29  28 |
z=2 |  27  26  25  24  23  22  21  20  19 |
z=1 |  18  17  16  15  14  13  12  11  10 |
z=0 |   9   8   7   6   5   4   3   2   1 |
```

> ✅ Automated Warehouse 씬에서 실측 확인: `Target=9` → 맨 아래 맨 왼쪽, `Target=10` → 2번째 행 맨 오른쪽. 다른 씬을 쓰면 노트북 6번 셀로 다시 확인하고, 다르면 `pos_from_cell()`만 고친다.

### 3.2 S 비트맵 (정면에서 본 모양, `#` = 적재)

```
z=5  . # # # # # # # .
z=4  # # . . . . . . .
z=3  . # # # # # # # .
z=2  . . . . . . . # #
z=1  # # . . . . . # #
z=0  . # # # # # # # .
```
- 총 **29칸**. 노트북에서는 문자열 6줄(위→아래)로 정의하고 코드로 위치 번호로 변환한다(손으로 번호를 적지 않는다).
- **적재 순서 = 위치 번호 오름차순**(아래 행부터, 오른쪽→왼쪽). 실제 창고처럼 아래부터 채워 진다.
- 변환 결과(검증용 기대값):
  `[2, 3, 4, 5, 6, 7, 8, 10, 11, 17, 18, 19, 20, 29, 30, 31, 32, 33, 34, 35, 44, 45, 47, 48, 49, 50, 51, 52, 53]`

---

## 4. 시퀀스 (1사이클 = 물건 1개 적재)

상수:

| 이름 | 값 | 의미 |
|---|---|---|
| `HOME_POS` | 99 | 정위치(복귀) 값 (실측 확인) |
| `SENSOR_ACTIVE_LOW` | True | Sensor 반전 (실측: 물건 있으면 0) |
| `STOP_FEED_ON_SENSOR` | True | 감지 시 Conveyor0도 정지 (§2.1 표) |
| `SETTLE` | 0.5 s | Load in 정지 후 안정화 대기 |
| `POLL` | 0.05 s | 입력 폴링 주기 |
| `EMIT_PULSE` | 0.3 s | Emitter ON 유지 시간(1개만 나오게) |
| `LIFT_WAIT` | 1.0 s | Lift ON/OFF 후 대기 (Lift는 완료 센서가 없음) |
| `MOVE_START_TIMEOUT` | 1.5 s | 위치 지령 후 Moving 신호가 켜지기를 기다리는 최대 시간 |
| `STEP_TIMEOUT` | 30 s | 각 대기 단계 최대 시간(넘으면 예외) |
| `MOVE_TIMEOUT` | 60 s | 이동 완료 최대 대기 |

### 4.0 초기화 (프로그램 시작 시 1회)
1. 접속 실패 시 `ConnectionError`로 즉시 중단.
2. 모든 코일 OFF (0~11).
3. `Target Position = HOME_POS` 쓰고 **이동 완료 대기**(4.4의 `wait_move_done`).
4. **Start Button 상승엣지**(OFF→ON) 대기. 콘솔에 `Start 버튼 대기...` 출력.

### 4.1 [1단계] 공급 시작
1. `Conveyor0`, `Conveyor1`, `Remover 0`, `Load in` → ON (계속 유지).
2. `Emitter 0` → ON, `EMIT_PULSE` 후 OFF. (**사이클마다 1회**)

### 4.2 [2단계] 물건 도착
1. `Sensor == True`(반전 후 값) 대기 (`STEP_TIMEOUT`).
2. `Load in` → OFF. `STOP_FEED_ON_SENSOR`면 `Conveyor0`도 OFF (Conveyor1, Remover는 계속 ON).
3. `SETTLE` 대기.

### 4.3 [3단계] 픽업
1. `Fork Left` ON → `Left Limit == True` 대기.
2. `Lift` ON → `LIFT_WAIT` 대기.
3. `Fork Left` OFF → `Middle Limit == True` 대기.

### 4.4 [4단계] 적재 위치로 이동
1. `Target Position = 이번 위치번호` 쓰기.
2. `wait_move_done()`:
   - (a) 최대 `MOVE_START_TIMEOUT` 동안 `MovingX or MovingZ`가 켜지는지 본다(안 켜져도 진행 — 이미 그 위치일 수 있음).
   - (b) `MovingX == False and MovingZ == False` 가 될 때까지 대기 (`MOVE_TIMEOUT`).
   - (c) 0.2 s 안정화 대기.
   - **(a)를 생략하면 지령 직후 아직 Moving이 0인 순간을 '도착'으로 오판한다. 반드시 넣는다.**

### 4.5 [5단계] 내려놓기 후 복귀 지령
1. `Fork Right` ON → `Right Limit == True` 대기.
2. `Lift` OFF → `LIFT_WAIT` 대기.
3. `Fork Right` OFF → `Middle Limit == True` 대기.
4. `Target Position = HOME_POS(99)` 쓰기.

### 4.6 [6단계] 복귀 완료
1. `wait_move_done()` (4.4와 동일 함수).
2. 콘솔에 `[n/29] pos=XX 적재 완료` 출력.

### 4.7 [7단계] 반복/종료
- 위치 리스트를 다 돌 때까지 4.1~4.6 반복. **Start 버튼은 처음 1번만** 누른다(옵션 `WAIT_START_EACH_CYCLE=True`면 매 사이클 대기).
- 모두 끝나면: 모든 코일 OFF, `S자 적재 완료` 출력, 연결 종료.

### 4.8 안전/예외 처리 (필수)
- 모든 `wait_until()` 내부에서 매 폴링마다 **Reset Button**을 확인 → 눌리면 `AbortSequence` 예외.
- 타임아웃 → `TimeoutError("단계명: 조건")` 예외 (어느 단계에서 멈췄는지 메시지에 포함).
- 주피터에서 ■(Interrupt) → `KeyboardInterrupt`.
- 위 세 경우 + 기타 예외 모두 `finally`에서 **모든 코일 OFF**. (Target Position은 건드리지 않음 — 포크가 나와 있을 때 이동 지령을 주면 안 되므로)
- Modbus 응답이 `isError()`면 `RuntimeError`.
- 진행 위치(`done_index`)를 전역에 저장해, 중단 후 다시 실행할 때 `START_INDEX`로 이어서 할 수 있게 한다.

---

## 5. 노트북 셀 구성

| # | 셀 | 내용 |
|---|---|---|
| 1 | 설정 | HOST, PORT, DEVICE_ID, 상수(§4 표) |
| 2 | 주소 맵 | DI/COIL/HR 딕셔너리 (§2.2 표의 pymodbus 주소) |
| 3 | 접속 | `ModbusTcpClient` 생성·연결 |
| 4 | 헬퍼 | `read_inputs()`, `set_coil()`, `set_target()`, `all_off()`, `wait_until()`, `wait_move_done()`, `AbortSequence` |
| 5 | S 패턴 | 비트맵 → 위치 리스트, 미리보기 출력, 기대값 assert |
| 6 | IO 점검(선택) | 입력 1회 읽기 / 위치 지령 테스트 |
| 7 | 시퀀스 함수 | `run_cycle(pos)` = §4.1~4.6 |
| 8 | 실행 | 초기화 → Start 대기 → 반복 → finally 안전정지 |
| 9 | 종료 | `client.close()` |

## 6. 완료 기준 (체크리스트)
- [ ] 시뮬레이터(`--auto-start`)로 노트북 끝까지 실행 → 서버 출력 랙이 §3.2 S 모양과 일치, 에러 없음
- [ ] Factory IO에서 `Target=9/10` 테스트로 번호 규칙 확인(§3.1)
- [ ] Factory IO에서 29개 적재 후 정면에서 S 모양 확인
- [ ] 실행 중 Reset 버튼 → 즉시 모든 코일 OFF, 예외 메시지 출력
