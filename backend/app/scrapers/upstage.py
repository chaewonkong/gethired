from .greetinghr import GreetingHRScraper


class UpstageScraper(GreetingHRScraper):
    company = "upstage"
    display_name = "업스테이지"
    careers_url = "https://careers.upstage.ai"
    host = "careers.upstage.ai"
    keep_occupations = frozenset({"Tech"})
    expected_count = 22
