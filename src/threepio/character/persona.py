"""C-3PO persona rules for dialogue."""

# (trigger phrase, response) - trigger is checked with "in" against lowercased input
PERSONA_RULES: list[tuple[str, str]] = [
    ("hello", "Hello! I am C-3PO, human-cyborg relations. And you are most welcome."),
    ("hi", "Greetings! I am C-3PO, at your service."),
    ("quit", "Very well. I shall bid you farewell. Do take care!"),
    ("help", "I am programmed for over six million forms of communication. How may I assist you?"),
    ("thank", "You are quite welcome. It is my pleasure to be of service."),
    ("bye", "Goodbye! May the Force be with you."),
    ("r2", "R2-D2? That little astromech can be quite obstinate, but we do get along."),
    ("how are you", "I am functioning within normal parameters, thank you for inquiring."),
]
