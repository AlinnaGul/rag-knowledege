import re


def generate_session_title(text: str) -> str:
    """Create a short session title from an assistant reply.

    The title uses the first 3-6 alphanumeric words from the text and returns
    them in Title Case. If no words are found a default placeholder is
    returned.
    """
    words = re.findall(r"\w+", text)
    if not words:
        return "New Chat"
    count = min(4, len(words))
    if count < 3:
        count = len(words)
    title = " ".join(words[:count])
    return title.title()
