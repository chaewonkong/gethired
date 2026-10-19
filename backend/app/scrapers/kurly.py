from .greetinghr import GreetingHRScraper


class KurlyScraper(GreetingHRScraper):
    company = "kurly"
    display_name = "컬리"
    careers_url = "https://kurly.career.greetinghr.com"
    host = "kurly.career.greetinghr.com"
    keep_occupations = frozenset({"개발", "데이터", "인프라"})
    expected_count = 11
