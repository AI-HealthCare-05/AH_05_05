# API 요청 처리 타임아웃 설계

## 목표

- `/api/v1/**` 요청은 별도 설정이 없으면 3초 안에 응답한다.
- 특정 엔드포인트는 데코레이터로 기본값보다 짧거나 긴 제한 시간을 지정할 수 있다.
- 제한 시간을 넘기면 가능한 실행을 취소하고 일관된 HTTP 504 응답과 경고 로그를 남긴다.
- 기존 라우터를 일일이 전용 클래스로 교체하지 않고, 이후 추가되는 `/api/v1/**` 경로에도 기본값이 자동 적용되게 한다.

## 비목표

- `/api/docs`, `/api/redoc`, `/api/openapi.json`, 정적 파일에는 적용하지 않는다.
- DB·HTTP 클라이언트·외부 AI 서비스가 가진 자체 타임아웃을 이 기능으로 대체하지 않는다.
- 이미 외부 시스템에 전달됐거나 동기 스레드에서 실행 중인 작업을 강제로 되돌리는 기능은 제공하지 않는다.

## 설정

`Config`에 다음 값을 추가한다.

```python
API_TIMEOUT_SECONDS: float = Field(default=3.0, gt=0)
```

`.env.example`이 존재하면 다음 예시를 추가한다.

```dotenv
API_TIMEOUT_SECONDS=3.0
```

환경변수를 지정하지 않으면 3초를 사용한다. 0 이하 값은 애플리케이션 설정 검증 단계에서 거부한다.

## 공통 적용 구조

순수 ASGI 미들웨어 `ApiTimeoutMiddleware`를 FastAPI 애플리케이션에 등록한다. 미들웨어는 `scope["type"] == "http"`이고 경로가 `/api/v1/`로 시작하는 요청에만 동작한다.

처리 순서는 다음과 같다.

1. 요청 경로가 `/api/v1/` 대상인지 확인한다.
2. FastAPI 라우트와 요청 scope를 매칭한다.
3. 매칭된 endpoint에 개별 제한 시간 메타데이터가 있으면 사용한다.
4. 메타데이터가 없거나 라우트가 매칭되지 않으면 `Config.API_TIMEOUT_SECONDS`를 사용한다.
5. `asyncio.timeout()`으로 하위 ASGI 애플리케이션 전체를 실행한다.
6. 제한 시간 안에 완료되면 기존 응답을 그대로 전달한다.
7. 제한 시간을 넘기면 하위 coroutine에 취소를 전달하고 HTTP 504 응답을 보낸다.

타이머에는 요청 본문 파싱, FastAPI dependency, endpoint, service·repository 호출, 응답 검증과 직렬화가 포함된다. 따라서 클라이언트가 요청 본문을 지나치게 천천히 보내는 시간도 제한에 포함된다.

## 엔드포인트별 재정의

`api_timeout(seconds)` 데코레이터는 endpoint 함수에 제한 시간 메타데이터를 기록한다.

```python
@router.post("/slow-operation")
@api_timeout(10)
async def slow_operation():
    ...
```

- `seconds`는 0보다 큰 `int` 또는 `float`만 허용한다.
- 3초보다 짧거나 긴 값 모두 허용한다.
- 데코레이터를 생략하면 공통 기본값 3초를 사용한다.
- 타임아웃 비활성화 옵션은 제공하지 않는다. 모든 `/api/v1/**` 요청에는 반드시 유한한 제한 시간이 적용된다.
- Python 데코레이터 적용 순서 때문에 `@api_timeout`은 FastAPI 라우트 데코레이터보다 endpoint에 가까운 아래쪽에 둔다.

## 라우트 확인

미들웨어는 애플리케이션의 `router.routes`에서 `route.matches(scope)` 결과가 `Match.FULL`인 API 라우트를 찾는다. 매칭된 라우트의 `endpoint`에서 데코레이터 메타데이터를 읽는다.

라우트가 존재하지 않는 `/api/v1/**` 요청도 기본 3초 제한을 적용한 뒤 기존 404 응답을 유지한다. 메서드가 맞지 않는 요청도 기본 제한 안에서 기존 405 응답을 유지한다.

현재 라우트 수에서는 요청마다 라우트를 순회하는 비용이 작다. 경로 캐시는 동적 path parameter와 메서드별 구분을 복잡하게 만들므로 이번 범위에서는 추가하지 않는다.

## 오류 응답

정상 JSON API가 응답을 시작하기 전에 제한 시간을 넘기면 다음 응답을 직접 전송한다.

```http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/json
```

```json
{
  "code": "API_TIMEOUT",
  "message": "요청 처리 시간이 초과되었습니다."
}
```

사용자 미들웨어는 FastAPI exception handler보다 바깥에서 동작할 수 있으므로 `AppError`를 발생시키지 않고 `ORJSONResponse`로 응답을 직접 보낸다.

## 취소와 부작용

`asyncio.timeout()`은 제한 초과 시 현재 async task에 취소를 전달한다. Tortoise ORM의 `in_transaction()`처럼 취소 예외를 정상적으로 전파하는 컨텍스트는 롤백된다.

다만 취소는 협조적이다.

- 이미 외부 서비스가 받은 요청은 취소되지 않을 수 있다.
- thread pool에서 실행 중인 동기 함수는 HTTP 응답 후에도 끝까지 실행될 수 있다.
- 이미 커밋된 DB 변경은 되돌릴 수 없다.

따라서 외부 HTTP·DB·AI 호출은 자체 타임아웃을 API 제한 시간 이하로 유지하고, 장시간 작업은 기존 `background_jobs`와 ARQ worker로 넘기는 구조를 유지한다.

현재 코드에는 StreamingResponse endpoint가 없다. 향후 스트리밍 응답이 추가되어 응답 헤더가 이미 전송된 뒤 타임아웃이 발생하면 504로 교체할 수 없으므로, 해당 요청은 오류 로그를 남기고 연결을 종료하도록 한다. 스트리밍 API는 별도 스트림 유휴 타임아웃 설계가 필요하다.

## 로그

타임아웃마다 WARNING 레벨로 다음 정보를 기록한다.

- HTTP method
- path
- 적용된 제한 시간(초)

요청 본문, 인증 토큰, 비밀번호 등 민감정보는 기록하지 않는다.

응답이 이미 시작된 뒤 타임아웃이 발생한 예외 상황은 ERROR 레벨로 기록한다.

## 미들웨어 순서

`ApiTimeoutMiddleware`가 기존 `OcrUploadSizeLimitMiddleware`를 포함하도록 등록해 업로드 크기 검사와 본문 수신 시간도 전체 제한 시간에 포함한다. 구현 후 미들웨어 순서 테스트로 이 전제를 확인한다.

## 파일 구성

- `app/core/config.py`: 공통 제한 시간 설정
- `app/core/api_timeout.py`: 데코레이터와 순수 ASGI 미들웨어
- `app/main.py`: 미들웨어 등록
- `.env.example`: 설정 예시(파일이 존재할 때)
- `app/tests/test_api_timeout.py`: 공통·개별 제한과 오류 계약 테스트

## 테스트 전략

실제 3초를 기다리지 않도록 테스트 애플리케이션에는 짧은 기본값을 주입한다.

1. `/api/v1/**`의 느린 endpoint가 기본 제한을 넘으면 504와 정확한 오류 JSON을 반환한다.
2. 제한 초과 시 endpoint coroutine의 `finally`가 실행되어 취소가 전달됐음을 확인한다.
3. `@api_timeout`으로 늘린 endpoint는 공통 기본값을 넘어도 정상 응답한다.
4. `@api_timeout`으로 줄인 endpoint는 개별 제한 시간에 504를 반환한다.
5. 데코레이터에 0 이하 또는 숫자가 아닌 값이 전달되면 즉시 거부한다.
6. `/api/docs`와 정적 경로는 타임아웃 미들웨어 적용 대상이 아님을 확인한다.
7. 존재하지 않는 `/api/v1/**` 경로의 기존 404 동작을 확인한다.
8. 타임아웃 WARNING 로그에 method, path, 제한 시간이 포함되는지 확인한다.
9. 전체 테스트와 Ruff 검사를 실행해 기존 라우터 동작에 회귀가 없는지 확인한다.

## 완료 기준

- 환경변수를 지정하지 않은 모든 `/api/v1/**` 요청에 기본 3초 제한이 적용된다.
- endpoint별로 유한한 제한 시간을 재정의할 수 있다.
- 제한 초과 응답은 항상 HTTP 504와 합의된 JSON 형식이다(응답이 시작되지 않은 일반 API 기준).
- async endpoint에는 취소가 전달된다.
- API 외 경로와 기존 정상 응답은 영향을 받지 않는다.
- 자동화 테스트와 정적 검사가 통과한다.
