from . import (  # noqa: F401  (registers scrapers)
    ably,
    bucketplace,
    coupang,
    daangn,
    dunamu,
    fortytwodot,
    hyperconnect,
    hyundai,
    kakao,
    kakaobank,
    kakaomobility,
    kakaopay,
    krafton,
    kurly,
    lablup,
    line,
    moloco,
    naver,
    nhn,
    samsung,
    toss,
    upstage,
    woowahan,
)
from .base import REGISTRY, RawPosting, Scraper, make_client

__all__ = ["REGISTRY", "RawPosting", "Scraper", "make_client"]
