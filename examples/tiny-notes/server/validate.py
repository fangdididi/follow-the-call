MAX_TITLE = 120


def clean_title(raw):
    title = " ".join(str(raw).split())
    return title[:MAX_TITLE]
