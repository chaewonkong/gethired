from .ninehire import NinehireScraper


class AblyScraper(NinehireScraper):
    company = "ably"
    display_name = "에이블리"
    careers_url = "https://ably.team/recruit"
    company_id = "423205c0-372b-11ee-a7cc-c92c3b459af0"
    site = "tydtr0dj"
    keep_groups = frozenset({"Engineering"})
    expected_count = 9
