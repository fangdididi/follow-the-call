import sqlite3


class NoteStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, title TEXT, body TEXT)")

    def insert_note(self, title, body):
        cur = self.db.execute("INSERT INTO notes (title, body) VALUES (?, ?)", (title, body))
        self.db.commit()
        return cur.lastrowid
