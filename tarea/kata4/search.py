"""
Kata 4 – Search functionality.

Provides a simple in-memory search across predefined city names.
"""

from typing import Iterable, List, Optional, Sequence


CITY_DATABASE: Sequence[str] = (
    "Paris",
    "Budapest",
    "Skopje",
    "Rotterdam",
    "Valencia",
    "Vancouver",
    "Amsterdam",
    "Vienna",
    "Sydney",
    "New York City",
    "London",
    "Bangkok",
    "Hong Kong",
    "Dubai",
    "Rome",
    "Istanbul",
)


def search_cities(search_text: str, cities: Optional[Iterable[str]] = None) -> List[str]:
    """
    Return a list of city names matching the provided search text.

    Rules
    -----
    * Fewer than 2 characters → no results.
    * Case insensitive comparison.
    * Matches when the search text is contained anywhere in the city name.
    * A literal '*' returns all available cities.
    """

    cities = tuple(cities) if cities is not None else CITY_DATABASE
    query = (search_text or "").strip()

    if query == "*":
        return list(cities)

    if len(query) < 2:
        return []

    lowered_query = query.lower()
    return [city for city in cities if lowered_query in city.lower()]
