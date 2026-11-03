# Trail: Saving a note
question: What happens between pressing "Save" in the editor and the note row existing in SQLite?
reader: a developer in their first week, comfortable with HTTP and SQL, new to this repo
start: the user submits the note form in the browser

## 1. The form is submitted
at: web/editor.js:4
quote: form.addEventListener("submit", async (event) => {
says: The editor stops the browser's normal form post and builds a plain object from the two fields. No validation happens on this side.
next: calls postNote
ask: If the title field is empty, does the browser still send a request?
answer: Yes. Nothing on the client checks the title; the server rejects it with 422.

## 2. The request leaves the browser
at: web/api.js:2
quote: const res = await fetch("/api/notes", {
says: postNote sends the object as JSON with POST to /api/notes and returns the parsed response body.
next: sends /api/notes

## 3. The server matches the route
at: server/routes.py:15
quote: app["routes"][("POST", "/api/notes")] = save_note
says: The route table maps POST /api/notes to the inner function save_note. This is registered once, at startup, from create_app.
next: calls save_note
ask: Where would you add a second endpoint, and which object must it close over to reach the database?
answer: In register_routes, next to this line; it closes over `store`.

## 4. The handler cleans the title
at: server/routes.py:9
quote: title = clean_title(request["json"].get("title", ""))
says: The title is normalised before anything else; a missing key becomes an empty string, which the next line turns into a 422.
next: calls clean_title

## 5. What "clean" means
at: server/validate.py:5
quote: title = " ".join(str(raw).split())
says: Runs of whitespace collapse to single spaces and the result is cut to MAX_TITLE (120) characters. Long titles are truncated silently, not rejected.
next: returns title
ask: A user pastes a 300-character title. What is stored, and does the user get told?
answer: The first 120 characters after whitespace collapse; no error is returned.

## 6. The handler stores the note
at: server/routes.py:12
quote: note_id = store.insert_note(title, request["json"].get("body", ""))
says: The cleaned title and the raw body go to the store. The body is not cleaned or length-limited.
next: calls insert_note

## 7. The row is written
at: server/store.py:10
quote: cur = self.db.execute("INSERT INTO notes (title, body) VALUES (?, ?)", (title, body))
says: A parameterised INSERT, committed immediately; the new row id travels back up as the 201 response's `id`, which the editor writes into `data-saved`.
ask: Is this INSERT safe against SQL injection through the title? Point to the reason.
answer: Yes: values are bound with `?` placeholders, never formatted into the SQL string.
