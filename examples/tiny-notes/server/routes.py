from .validate import clean_title
from .store import NoteStore


def register_routes(app):
    store: NoteStore = app["store"]

    def save_note(request):
        title = clean_title(request["json"].get("title", ""))
        if not title:
            return {"status": 422, "error": "title required"}
        note_id = store.insert_note(title, request["json"].get("body", ""))
        return {"status": 201, "id": note_id}

    app["routes"][("POST", "/api/notes")] = save_note
    return app
