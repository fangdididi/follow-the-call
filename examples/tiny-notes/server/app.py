"""Tiny notes service used by the follow-the-call examples."""
from .routes import register_routes
from .store import NoteStore


def create_app(db_path="notes.db"):
    store = NoteStore(db_path)
    app = {"routes": {}, "store": store}
    register_routes(app)
    return app


if __name__ == "__main__":
    create_app()
