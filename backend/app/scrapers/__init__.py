from . import (  # noqa: F401  (registers scrapers)
    coupang, daangn, fortytwodot, hyperconnect, hyundai, kakao, kakaopay, line, naver, samsung, toss, upstage,
)
from .base import REGISTRY, RawPosting, Scraper, make_client

__all__ = ["REGISTRY", "RawPosting", "Scraper", "make_client"]
