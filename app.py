from flask import Flask, request, jsonify, render_template, g
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
DATABASE = 'library.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT UNIQUE NOT NULL,
            available INTEGER DEFAULT 1
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            book_id INTEGER,
            loan_date TEXT,
            return_date TEXT,
            returned INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(book_id) REFERENCES books(id)
        )""")
        conn.commit()

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/books')
def get_books():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT books.id, books.title, books.author, books.isbn, books.available,
                   users.name
            FROM books
            LEFT JOIN loans ON books.id = loans.book_id AND loans.returned = 0
            LEFT JOIN users ON loans.user_id = users.id
        """)
        books = cursor.fetchall()
        return jsonify([
            {
                "id": b[0], "title": b[1], "author": b[2],
                "isbn": b[3], "available": b[4],
                "borrowed_by": b[5]
            } for b in books
        ])

@app.route('/loans')
def get_loans():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT books.title, books.author, books.isbn, users.name, loans.loan_date, loans.return_date
            FROM loans
            JOIN users ON loans.user_id = users.id
            JOIN books ON loans.book_id = books.id
            WHERE loans.returned = 0
        """)
        data = cursor.fetchall()
        return jsonify([
            {
                "title": d[0], "author": d[1], "isbn": d[2],
                "user": d[3], "loan_date": d[4], "return_date": d[5]
            } for d in data
        ])

@app.route('/add_book', methods=['POST'])
def add_book():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    title = data.get('title')
    author = data.get('author')
    isbn = data.get('isbn')

    if not title or not author or not isbn:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO books (title, author, isbn) VALUES (?, ?, ?)",
                           (title, author, isbn))
            conn.commit()
        return jsonify({"message": "Book added successfully"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "ISBN already exists"}), 409

@app.route('/loan_book', methods=['POST'])
def loan_book():
    data = request.get_json()
    user_name = data.get('user_name')
    isbn = data.get('book_isbn')

    if not user_name or not isbn:
        return jsonify({"error": "Missing name or ISBN"}), 400

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE name = ?", (user_name,))
        user = cursor.fetchone()
        if not user:
            cursor.execute("INSERT INTO users (name) VALUES (?)", (user_name,))
            user_id = cursor.lastrowid
        else:
            user_id = user[0]

        cursor.execute("SELECT id, available FROM books WHERE isbn = ?", (isbn,))
        book = cursor.fetchone()
        if not book:
            return jsonify({"error": "Book not found"}), 404
        if book[1] == 0:
            return jsonify({"error": "Book not available"}), 400

        loan_date = datetime.now().strftime("%Y-%m-%d")
        return_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        cursor.execute("INSERT INTO loans (user_id, book_id, loan_date, return_date) VALUES (?, ?, ?, ?)",
                       (user_id, book[0], loan_date, return_date))
        cursor.execute("UPDATE books SET available = 0 WHERE id = ?", (book[0],))
        conn.commit()

    return jsonify({"message": "Book loaned successfully"})

@app.route('/return_book', methods=['POST'])
def return_book():
    data = request.get_json()
    isbn = data.get('book_isbn')

    if not isbn:
        return jsonify({"error": "Missing ISBN"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM books WHERE isbn = ?", (isbn,))
        book = cursor.fetchone()
        if not book:
            return jsonify({"error": "Book not found"}), 404

        cursor.execute("UPDATE loans SET returned = 1 WHERE book_id = ? AND returned = 0", (book[0],))
        cursor.execute("UPDATE books SET available = 1 WHERE id = ?", (book[0],))
        conn.commit()

    return jsonify({"message": "Book returned successfully"})

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
