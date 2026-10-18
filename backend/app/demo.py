"""데모 모드: 스크래퍼·프로필·판정을 고정 데이터로 바꾼 백엔드. 네트워크·LLM·CLI·실제 경로를 쓰지 않는다.
모든 텍스트는 가상이다."""
import asyncio
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import create_app
from .config import FRONTEND_DIST
from .jobs import JobManager
from .matcher import Match
from .profile import Preferences, Profile
from .repository import Repository, set_fixed_now
from .scrapers import RawPosting, Scraper

FIXED_NOW = "2026-10-18T09:00:00+09:00"
DEMO_JUDGE_DELAY_S = 0.7

COMPANIES = ("toss", "daangn", "kakao", "naver")


def _url(company: str, n: int) -> str:
    return f"https://example.com/demo/{company}/{n}"


POSTINGS: dict[str, list[RawPosting]] = {
    "toss": [
        RawPosting(company="toss", external_id="demo-toss-1", title="서버 개발자 (Go)", apply_url=_url("toss", 1),
                   category="Engineering",
                   description="Go로 대규모 트래픽을 처리하는 코어 서버를 개발합니다. Redis·Kubernetes 기반 운영 경험과 "
                               "분산 시스템 설계 경험을 우대합니다. 5년 이상의 백엔드 경력을 기대합니다."),
        RawPosting(company="toss", external_id="demo-toss-2", title="결제 플랫폼 백엔드", apply_url=_url("toss", 2),
                   category="Engineering",
                   description="결제 승인·정산 파이프라인을 설계하고 운영합니다. Kotlin 또는 Go, PostgreSQL, "
                               "메시지 큐 경험을 요구하며 금융 도메인 경험은 우대입니다."),
    ],
    "daangn": [
        RawPosting(company="daangn", external_id="demo-daangn-1", title="매칭 플랫폼 백엔드 엔지니어",
                   apply_url=_url("daangn", 1), category="Software Engineer", deadline=date(2026, 10, 22),
                   description="이웃 간 거래·모임을 연결하는 매칭 플랫폼의 백엔드를 만듭니다. Go, Redis, Kubernetes 환경에서 "
                               "지연과 공정성을 함께 다루는 매칭 로직을 설계·운영한 경험을 찾습니다."),
        RawPosting(company="daangn", external_id="demo-daangn-2", title="데이터 플랫폼 엔지니어",
                   apply_url=_url("daangn", 2), category="Software Engineer",
                   description="이벤트 수집 파이프라인과 분석용 저장소를 운영합니다. Spark·Airflow·ClickHouse 등 "
                               "데이터 인프라 경험과 Python 기반 배치 개발 경험을 요구합니다."),
    ],
    "kakao": [
        RawPosting(company="kakao", external_id="demo-kakao-1", title="게임 서버 백엔드 (Kotlin)",
                   apply_url=_url("kakao", 1), category="서버",
                   description="모바일 게임의 매치메이킹·랭킹·보상 서버를 개발합니다. Kotlin/Spring 필수, "
                               "실시간 트래픽 처리와 Redis 기반 세션 관리 경험을 우대합니다."),
        RawPosting(company="kakao", external_id="demo-kakao-2", title="인프라 엔지니어", apply_url=_url("kakao", 2),
                   category="인프라",
                   description="사내 Kubernetes 플랫폼과 관측 스택을 운영합니다. Terraform·Ansible 기반 프로비저닝, "
                               "네트워크·스토리지 운영 경험을 요구합니다."),
    ],
    "naver": [
        RawPosting(company="naver", external_id="demo-naver-1", title="검색 플랫폼 백엔드 (Java)",
                   apply_url=_url("naver", 1), category="Tech",
                   description="검색 색인·질의 서빙 플랫폼을 개발합니다. Java/Spring 필수, 대용량 분산 저장소 운영 경험과 "
                               "검색 품질 개선 경험을 우대합니다."),
        RawPosting(company="naver", external_id="demo-naver-2", title="실시간 메시징 서버", apply_url=_url("naver", 2),
                   category="Tech",
                   description="수천만 사용자가 쓰는 실시간 메시징 서버를 개발합니다. Go 또는 Java, 분산 시스템과 "
                               "WebSocket·pub/sub 설계 경험을 요구합니다."),
    ],
}


class DemoScraper(Scraper, register=False):
    expected_count: ClassVar[int] = 2

    async def fetch(self, client: httpx.AsyncClient) -> list[RawPosting]:
        return list(POSTINGS[self.company])


class DemoToss(DemoScraper, register=False):
    company = "toss"
    display_name = "토스"
    careers_url = "https://toss.im/career/jobs"


class DemoDaangn(DemoScraper, register=False):
    company = "daangn"
    display_name = "당근"
    careers_url = "https://about.daangn.com/jobs/"


class DemoKakao(DemoScraper, register=False):
    company = "kakao"
    display_name = "카카오"
    careers_url = "https://careers.kakao.com/jobs"


class DemoNaver(DemoScraper, register=False):
    company = "naver"
    display_name = "네이버"
    careers_url = "https://recruit.navercorp.com/rcrt/list.do"


SCRAPERS: dict[str, type[Scraper]] = {"toss": DemoToss, "daangn": DemoDaangn, "kakao": DemoKakao, "naver": DemoNaver}

PROFILE = Profile(
    name="홍길동", seniority="senior", years_experience=5,
    core_skills=["Go", "Redis", "Kubernetes", "PostgreSQL"],
    familiar_skills=["TypeScript", "gRPC", "ClickHouse"],
    weak_or_learning=["Kotlin", "Java"],
    domains=["매치메이킹", "실시간 게임 서버"],
    notable_achievements=["매칭 대기 시간을 40% 줄인 큐 재설계", "피크 동시접속 50만 매칭 서버 무중단 운영"],
    preferences=Preferences(locations=["서울"], visa_or_work_authorization=None,
                            target_domains=["매치메이킹", "실시간 플랫폼"], target_roles=["백엔드 엔지니어"]),
    dealbreakers=["프론트엔드 전담", "주니어 포지션"],
    summary="Go 기반 매치메이킹 서버를 5년간 설계·운영한 백엔드 엔지니어. Redis·Kubernetes·PostgreSQL이 주력이다.",
)


def _match(eid: str, level: str, score: int, summary: str, tech: list[str], gaps: list[str], reason: str) -> Match:
    return Match(external_id=eid, fit_level=level, score=score, gaps=gaps, summary=summary, tech_stack=tech,
                 fit_reason=reason)


MATCHES: dict[str, Match] = {m.external_id: m for m in [
    _match("demo-toss-1", "strong", 90, "Go로 코어 서버를 개발하는 백엔드 포지션.", ["Go", "Redis", "Kubernetes"], [],
           "주력 스택인 Go·Redis·Kubernetes가 공고 요구와 그대로 겹치고, 대규모 매칭 서버 무중단 운영 경험이 "
           "대규모 트래픽 처리 요구에 직접 대응합니다. 연차도 5년 이상 조건에 맞습니다."),
    _match("demo-toss-2", "good", 74, "결제 승인·정산 파이프라인을 만드는 백엔드 포지션.", ["Kotlin", "Go", "PostgreSQL"],
           ["domain: 금융·결제 도메인 경험 없음"],
           "Go와 PostgreSQL 경험이 핵심 요구와 맞고 분산 시스템 운영 경험도 유효하지만, 결제·정산 도메인 경험이 없어 "
           "우대 요건에서 점수를 잃습니다."),
    _match("demo-daangn-1", "strong", 92, "이웃 매칭 플랫폼의 백엔드를 설계·운영하는 포지션.", ["Go", "Redis", "Kubernetes"], [],
           "매칭 로직의 지연과 공정성을 다루는 포지션으로, 매칭 대기 시간을 40% 줄인 큐 재설계 경험이 그대로 들어맞습니다. "
           "Go·Redis·Kubernetes 스택도 동일합니다."),
    _match("demo-daangn-2", "stretch", 56, "이벤트 파이프라인과 분석 저장소를 운영하는 데이터 플랫폼 포지션.",
           ["Spark", "Airflow", "ClickHouse", "Python"],
           ["framework: Spark·Airflow 경험 없음", "language: Python 배치 개발이 주력이 아님"],
           "ClickHouse 운영 경험이 있어 저장소 쪽은 접점이 있지만, Spark·Airflow 기반 파이프라인과 Python 배치 개발이 "
           "주력이 아니라 서류 리스크가 있습니다."),
    _match("demo-kakao-1", "good", 70, "모바일 게임의 매치메이킹·랭킹 서버를 만드는 포지션.", ["Kotlin", "Spring", "Redis"],
           ["language: Kotlin/Spring 필수, 지원자는 Go 주력"],
           "게임 매치메이킹 도메인과 Redis 세션 관리 경험이 공고와 정확히 겹칩니다. 다만 Kotlin/Spring이 필수라 "
           "언어 전환이 필요해 한 단계 낮췄습니다."),
    _match("demo-kakao-2", "stretch", 52, "사내 Kubernetes 플랫폼과 관측 스택을 운영하는 인프라 포지션.",
           ["Kubernetes", "Terraform", "Ansible"],
           ["other: 애플리케이션 개발이 아닌 인프라 운영 중심", "framework: Terraform·Ansible 경험 없음"],
           "Kubernetes 운영 경험은 맞지만 역할이 인프라 프로비저닝과 네트워크·스토리지 운영에 치우쳐 있어 "
           "백엔드 개발 경력과는 거리가 있습니다."),
    _match("demo-naver-1", "stretch", 58, "검색 색인·질의 서빙 플랫폼을 개발하는 백엔드 포지션.", ["Java", "Spring"],
           ["language: Java/Spring 필수, 지원자는 Go 주력", "domain: 검색 도메인 경험 없음"],
           "대용량 분산 저장소 운영 경험은 유효하지만 Java/Spring이 필수이고 검색 도메인 경험이 없어 "
           "역할은 맞되 서류 통과 리스크가 큽니다."),
    _match("demo-naver-2", "good", 72, "대규모 실시간 메시징 서버를 개발하는 백엔드 포지션.", ["Go", "Java", "WebSocket"],
           ["domain: 메시징 서비스 경험 없음"],
           "Go와 분산 시스템 설계 경험이 요구와 맞고, 실시간 게임 서버 운영 경험이 실시간 메시징 트래픽 처리에 "
           "전이됩니다. 메시징 도메인 자체는 처음이라 good에 둡니다."),
]}


async def load_profile(repo: Repository) -> Profile:
    return PROFILE


async def judge(profile: Profile, postings: list[RawPosting]) -> tuple[list[Match], list[Any]]:
    await asyncio.sleep(float(os.environ.get("DEMO_JUDGE_DELAY_S", DEMO_JUDGE_DELAY_S)))
    return [MATCHES[p.external_id].model_copy() for p in postings], []


async def logged_in(provider: str) -> bool:
    return True


def make_app() -> FastAPI:
    set_fixed_now(FIXED_NOW)
    tmp: Path | None = None

    def temp_path(name: str) -> Path:
        nonlocal tmp
        tmp = tmp or Path(tempfile.mkdtemp(prefix="job-posting-demo-"))
        return tmp / name

    db_path = Path(os.environ.get("DB_PATH") or temp_path("app.db"))
    resume_dir = Path(os.environ.get("RESUME_DIR") or temp_path("resume"))

    repo = Repository(db_path)
    jobs = JobManager(repo, scrapers=dict(SCRAPERS), profile_loader=load_profile, judge_fn=judge)
    app = create_app(repo, jobs, logged_in=logged_in, resume_dir=resume_dir)
    app.state.db_path, app.state.resume_dir = db_path, resume_dir
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app
