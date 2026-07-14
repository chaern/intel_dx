# 예시 도서 데이터
books = [
    {"title": "파이썬 입문", "author": "홍길동", "publisher": "ABC출판사"},
    {"title": "자료구조", "author": "김철수", "publisher": "IT북스"},
    {"title": "알고리즘", "author": "이영희", "publisher": "코딩출판"},
    {"title": "파이썬 실전", "author": "박민수", "publisher": "ABC출판사"}
]


# ---------------- 검색 기능 ----------------
def search_by_title(books, keyword):
    return [book for book in books
            if keyword.lower() in book["title"].lower()]


def search_by_author(books, keyword):
    return [book for book in books
            if keyword.lower() in book["author"].lower()]


def search_by_publisher(books, keyword):
    return [book for book in books
            if keyword.lower() in book["publisher"].lower()]


def search_book():
    print("\n===== 책 검색 =====")
    print("1. 제목 검색")
    print("2. 저자 검색")
    print("3. 출판사 검색")

    choice = input("검색 방법 선택 >> ")
    keyword = input("검색어 입력 >> ")

    if choice == "1":
        result = search_by_title(books, keyword)

    elif choice == "2":
        result = search_by_author(books, keyword)

    elif choice == "3":
        result = search_by_publisher(books, keyword)

    else:
        print("잘못된 입력입니다.")
        return

    if result:
        print("\n===== 검색 결과 =====")
        for book in result:
            print(f"제목 : {book['title']}")
            print(f"저자 : {book['author']}")
            print(f"출판사 : {book['publisher']}")
            print("-" * 30)
    else:
        print("검색 결과가 없습니다.")


# ---------------- 메뉴 ----------------
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
            print("책 추가 기능 실행")
            # add_book()

        elif choice == "2":
            print("책 조회 기능 실행")
            # view_books()

        elif choice == "3":
            search_book()      # 검색 기능 연결

        elif choice == "4":
            print("책 삭제 기능 실행")
            # delete_book()

        elif choice == "0":
            print("프로그램을 종료합니다.")
            break

        else:
            print("잘못된 입력입니다. 다시 선택해주세요.")


# 프로그램 실행
main()
