import os

from starlette.responses import Response
from starlette.staticfiles import PathLike, StaticFiles
from starlette.types import Scope

# no-store 가 아니라 no-cache 다. 캐시는 하되 쓸 때마다 서버에 물어본다.
# 안 바뀌었으면 etag 로 304 가 오므로 본문을 다시 받지 않는다.
CACHE_CONTROL = "no-cache"


class NoCacheStaticFiles(StaticFiles):
    """정적 파일 응답에 Cache-Control: no-cache 를 붙인다.

    기본 StaticFiles 는 etag·last-modified 만 주고 Cache-Control 을 주지 않는다.
    그러면 브라우저가 heuristic caching 으로 임의 기간 재검증 없이 캐시를 쓰는데,
    관리자 콘솔에서 실제 문제가 됐다 — 화면을 고쳐도 반영되지 않아 하드 리로드가
    필요했고, 회원 상세 보기가 옛 HTML 로 깨졌다(#118).

    ?v= 쿼리를 손으로 붙이는 방식으로 버텼으나 세 가지 이유로 무너졌다.

    1. ES 모듈 import 는 부모의 쿼리를 물려받지 않는다. `<script src="x.js?v=1">`
       안에서 `import "./api.js"` 하면 쿼리 없이 요청되므로 api.js·overlay.js·
       navigation.js 는 무효화 수단이 아예 없었다.
    2. 파일마다 호출부마다 사람이 올려야 해서 빠뜨린다(#118 이 그 사례다).
    3. 버전 줄이 병합 충돌을 일으킨다.

    서버가 헤더로 지시하면 위 세 가지가 모두 사라진다. import 경로든 fetch 경로든
    같은 응답을 받기 때문이다.

    적용 범위는 app/static/ 마운트뿐이다. frontend/ (React)는 Vite 가 해시 파일명을
    만들어 주므로 장기 캐시가 맞고 여기 규칙을 적용하지 않는다.
    """

    def file_response(
        self,
        full_path: PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code=status_code)
        # super() 는 조건부 요청이면 NotModifiedResponse(304)를 돌려준다. 그 클래스는
        # 헤더를 화이트리스트로 걸러 만드는데, 필터링이 끝난 객체에 붙이므로 304 에도 남는다.
        # 304 에 이 헤더가 없으면 브라우저가 다음 요청부터 다시 heuristic caching 으로 돌아간다.
        response.headers["Cache-Control"] = CACHE_CONTROL
        return response
