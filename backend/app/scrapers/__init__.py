from . import (  # noqa: F401  (registers scrapers)
    coupang,
    daangn,
    dunamu,
    fortytwodot,
    hyperconnect,
    hyundai,
    kakao,
    kakaobank,
    kakaopay,
    line,
    naver,
    samsung,
    toss,
    upstage,
    woowahan,
)
from .base import REGISTRY, RawPosting, Scraper, make_client

__all__ = ["REGISTRY", "RawPosting", "Scraper", "make_client"]
