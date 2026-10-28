"""Held-out cases: written AFTER the prompt change, so the prompt was not tuned on them."""
from suite import MODEL, build   # same agent setup, including the PROMPT=v2 switch

from agentlens.testing import Case, contains, number_equals

SUITE = "sample-agent-heldout"

CASES = [
    Case("units-books-bags", "How many units of books and bags were sold together?", number_equals(55)),
    Case("price-gap", "How much more does a bag cost than a pen?", number_equals(395)),
    Case("plain-division", "What is 250 divided by 8?", number_equals(31.25)),
    Case("budget-double", "What is the approved budget in notes.txt multiplied by 2?", number_equals(90000)),
    Case("fewest-units", "Which item sold the fewest units?", contains("bags")),
    Case("cheapest", "What is the lowest price in sales.csv?", number_equals(5)),
]