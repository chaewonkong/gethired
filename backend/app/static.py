from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope


def is_client_route(path: str) -> bool:
    """확장자 없는 마지막 세그먼트 = 클라이언트 라우트. api/는 라우터가 먼저 받지만 방어적으로 제외"""
    path = path.lstrip("/")
    return not (path == "api" or path.startswith("api/")) and "." not in path.rsplit("/", 1)[-1]


class SPAStaticFiles(StaticFiles):
    """/postings/1 같은 클라이언트 경로는 index.html로 fallback"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            res = await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code != 404 or not is_client_route(path):
                raise
        else:
            if res.status_code != 404 or not is_client_route(path):
                return res
        return await super().get_response("index.html", scope)
