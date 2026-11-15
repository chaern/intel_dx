# 도서 관리 프로그램

# 책 저장 함수
def add_book():
    title = input("책 제목: ")
    author = input("저자: ")
    price = input("가격: ")

    with open("books.txt", "a", encoding="utf-8") as file:
        file.write(f"{title},{author},{price}\n")

    print("책 정보가 저장되었습니다.")


# 메뉴 화면
def show_menu():
    print("\n===== 도서 관리 프로그램 =====")
    print("1. 책 추가")
    print("2. 책 조회")
    print("3. 책 검색")
    print("4. 책 삭제")
    print("0. 프로그램 종료")


def main():
    while True:
        show_menu()

        choice = input("메뉴 선택 >> ")

        if choice == "1":
            add_book()      # 저장 기능 연결

        elif choice == "2":
            print("책 조회 기능 실행")
            # view_books() 연결 예정

        elif choice == "3":
            print("책 검색 기능 실행")
            # search_book() 연결 예정

        elif choice == "4":
            print("책 삭제 기능 실행")
            # delete_book() 연결 예정

        elif choice == "0":
            print("프로그램을 종료합니다.")
            break

        else:
            print("잘못된 입력입니다. 다시 선택해주세요.")


# 프로그램 실행
main()