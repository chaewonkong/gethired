from .greetinghr import GreetingHRScraper


class KakaoMobilityScraper(GreetingHRScraper):
    company = "kakaomobility"
    display_name = "카카오모빌리티"
    careers_url = "https://kakaomobility.career.greetinghr.com"
    host = "kakaomobility.career.greetinghr.com"
    keep_occupations = frozenset({"기술"})
    expected_count = 13
