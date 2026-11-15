# 간단한 파이썬 계산기 프로그램

def calculator():
    print("=== 간단한 계산기 ===")
    
    num1 = float(input("첫 번째 숫자 입력: "))
    op = input("연산자 입력 (+, -, *, /): ")
    num2 = float(input("두 번째 숫자 입력: "))

    if op == "+":
        result = num1 + num2
    elif op == "-":
        result = num1 - num2
    elif op == "*":
        result = num1 * num2
    elif op == "/":
        if num2 == 0:
            print("0으로 나눌 수 없습니다.")
            return
        result = num1 / num2
    else:
        print("지원하지 않는 연산자입니다.")
        return

    print("결과:", result)


calculator()