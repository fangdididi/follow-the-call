import { postNote } from "./api.js";

export function mountEditor(form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const note = { title: form.title.value, body: form.body.value };
    const result = await postNote(note);
    form.dataset.saved = result.id ?? "";
  });
}
