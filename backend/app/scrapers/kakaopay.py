from .greetinghr import GreetingHRScraper


class KakaoPayScraper(GreetingHRScraper):
    company = "kakaopay"
    display_name = "카카오페이"
    careers_url = "https://careers.kakaopay.com"
    host = "careers.kakaopay.com"
    keep_occupations = frozenset({"기술"})
    expected_count = 10
