import html as html_mod
import re
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, Field

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)


class RawPosting(BaseModel):
    company: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    apply_url: str = Field(pattern=r"^https?://")
    deadline: date | None = None
    description: str | None = None
    category: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


REGISTRY: dict[str, type["Scraper"]] = {}


class Scraper(ABC):
    company: ClassVar[str]
    display_name: ClassVar[str]
    careers_url: ClassVar[str]
    expected_count: ClassVar[int]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "company" in cls.__dict__:
            REGISTRY[cls.company] = cls

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]: ...


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": UA},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )


_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_BLOCK_RE = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|table|section)[^>]*>", re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(s: str | None) -> str | None:
    if not s:
        return None
    s = _TAG_RE.sub(" ", s)
    s = _BLOCK_RE.sub("\n", s)
    s = _ANY_TAG_RE.sub(" ", s)
    s = html_mod.unescape(s).replace("﻿", "").replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip() or None


def parse_date(s: str | None, fmt: str) -> date | None:
    if not s:
        return None
    from datetime import datetime

    width = len(date(2000, 1, 1).strftime(fmt))
    try:
        return datetime.strptime(s[:width], fmt).date()
    except ValueError:
        return None
