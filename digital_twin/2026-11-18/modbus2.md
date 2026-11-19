# [MODBUS TCP] py으로 통신

> **📓 ipynb 분석 요약** (modbus_py.ipynb)

## 주제/목적
Modbus TCP 클라이언트를 사용하여 특정 디바이스(IP: 192.168.0.226)와 통신하며, 입력 값을 스캔하고 제어 로직에 따라 코일을 쓰기하는 코드입니다.

## 주요 흐름
*   Modbus TCP 클라이언트를 생성하고 지정된 IP와 포트로 연결합니다.
*   `read_discrete_inputs` 함수를 사용하여 디바이스의 초기 상태(8개 비트)를 주기적으로 읽어옵니다.
*   초기 스캔 결과를 바탕으로 제어 로직을 수행합니다.
    *   'Emitter'와 'Remover' 코일을 활성화합니다.
    *   `startbtn` 비트가 활성화되면 컨베이어 정방향 코일을 켜고, 역방향 코일을 끕니다.
    *   `sensor` 비트가 활성화되면 카운터를 증가시키고, 레지스터에 값을 씁니다. 이후 특정 시간 동안 제어 코일을 활성화/비활성화합니다.
*   `tt.sleep`을 사용하여 각 작업 간의 지연 시간을 설정합니다.

## 사용 기술
*   `pymodbus` 라이브러리 (특히 `ModbusTcpClient`)
*   Modbus TCP 통신 (IP, Port, `read_discrete_inputs`, `write_coil`, `write_register`)
*   Python 기본 제어문 (for 루프, if 조건문)
*   `time` 라이브러리 (`tt.sleep`)

## 결과/결론
*   Modbus TCP 클라이언트 연결 성공 여부 (`True` 출력).
*   초기 입력 값 스캔 결과 (예: `[False, False, True, True, False, False, False, False]`).
*   제어 로직 실행 중 입력 값 스캔 결과가 실시간으로 출력됩니다.
*   `client` 객체의 사용 가능한 메소드 목록을 보여주는 `dir(client)` 결과가 출력됩니다.

---

## FACTORY IO 를 PY 로 연결

![image](/attachments/card-1791430012135-0beb26c7-6d60-44e7-b06f-d170082a2c03/paste_1777272920038_ticqm.png)

```py
from pymodbus.client import ModbusTcpClient
import time
ip = '192.168.0.226'
port = 502
client = ModbusTcpClient(ip,port=port)
client.connect()
print("서버연결, 디지털 트윈시스템 시작!")

```
```py
# 디지털입력
r = client.read_discrete_inputs(address=0, count=8) # 10001 ~ 10009
print(r.bits)
```
```py
# 디지털출력
client.write_coil(0,False)
```
```py
# 아날로그입력
ai = client.read_input_registers(address=0,count=8)
print(ai.registers)
```
```py
# 아날로그출력
client.write_register(0,1234)
```
```py
# 제어 테스트
for n in range(100):
    r = client.read_discrete_inputs(address=0, count=8)
    if r.bits[0]==True:
        print(r.bits[0])
        client.write_coil(0,True)
    time.sleep(0.1)
```

#MODBUS TCP #Python #FACTORY IO #제어 #통신 #modbus #python  #pymodbus
