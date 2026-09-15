# AWS HTTPS / 프론트 설정 복구

운영 디렉터리는 `/home/ubuntu/rxvita`입니다. 이 변경은 이미지 버전이나 DB를 변경하지 않습니다.
`scripts/deployment.sh`는 `~/project`로 설정 파일을 덮어쓰는 기존 스크립트이므로 이 복구에 사용하지 않습니다.

## 적용 전 확인

- AWS `.env`를 보존합니다. 로컬 `.prod.env`로 덮어쓰지 않습니다.
- 인증서 `/etc/letsencrypt/live/api.rxvita.p-e.kr/{fullchain,privkey}.pem`이 Nginx 컨테이너에 있어야 합니다.
- AWS `/home/ubuntu/rxvita/frontend/dist/index.html`과 해당 빌드의 assets가 있어야 합니다.
  기존 프론트 파일이 다른 위치에 있다면 먼저 확인하고 전체 빌드 결과를 이 위치에 복사합니다.
- AWS Compose와 로컬 운영 Compose를 비교하여 운영 전용 설정을 보존합니다.
  특히 이미지 버전, 네트워크, 볼륨 이름을 임의로 변경하지 않습니다.

## 변경할 부분

1. 현재 AWS `nginx/default.conf`와 `docker-compose.yml`을 백업합니다.
2. 로컬 `infra/nginx/prod_https.conf`를 AWS `nginx/default.conf`에 반영합니다.
   `prod_http.conf`는 인증서 최초 발급용이며 HTTPS 운영 설정을 대체하면 안 됩니다.
3. AWS Compose의 nginx.volumes에 다음 항목을 추가합니다.

```yaml
- ./frontend/dist:/usr/share/nginx/html:ro
```

4. fastapi.volumes의 기존 배지 저장 연결도 보존합니다.

```yaml
- ./uploads/badges:/app/app/static/media/badges
```

## AWS에서 검증 및 적용

```bash
cd /home/ubuntu/rxvita
test -s frontend/dist/index.html
docker compose config --quiet
docker compose run --rm --no-deps nginx nginx -t
docker compose up -d --no-deps --force-recreate nginx
curl --fail --head https://api.rxvita.p-e.kr/login
curl --fail --head https://api.rxvita.p-e.kr/api/openapi.json
```

프론트 응답은 HTML이어야 하고 JS/CSS 자산도 각각 올바른 Content-Type으로 응답해야 합니다.
`docker compose down -v`나 DB 마이그레이션 초기화는 실행하지 않습니다.
실패하면 백업한 Nginx·Compose 설정을 복원하고 nginx만 재생성합니다.
