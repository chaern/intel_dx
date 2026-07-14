import json
import os

FILE_NAME = "books.json"


class BookManager:
    def __init__(self):
        self.books = []
        self.load_books()

    def add_book(self, title, author, price):
        book = {
            "title": title,
            "author": author,
            "price": price
        }
        self.books.append(book)
        self.save_books()
        print("도서가 저장되었습니다.")

    def save_books(self):
        with open(FILE_NAME, "w", encoding="utf-8") as file:
            json.dump(self.books, file, ensure_ascii=False, indent=4)

    def load_books(self):
        if os.path.exists(FILE_NAME):
            with open(FILE_NAME, "r", encoding="utf-8") as file:
                self.books = json.load(file)

    def show_books(self):
        if not self.books:
            print("등록된 도서가 없습니다.")
            return

        print("\n=== 도서 목록 ===")
        for i, book in enumerate(self.books, start=1):
            print(f"{i}. 제목 : {book['title']}")
            print(f"   저자 : {book['author']}")
            print(f"   가격 : {book['price']}원")
            print("-" * 30)


def main():
    manager = BookManager()

    while True:
        print("\n===== 도서 관리 =====")
        print("1. 도서 추가")
        print("2. 도서 목록 조회")
        print("3. 종료")

        menu = input("메뉴 선택: ")

        if menu == "1":
            title = input("도서명: ")
            author = input("저자: ")
            price = int(input("가격: "))
            manager.add_book(title, author, price)

        elif menu == "2":
            manager.show_books()

        elif menu == "3":
            print("프로그램을 종료합니다.")
            break

        else:
            print("잘못된 입력입니다.")


if __name__ == "__main__":
    main()