#!/usr/bin/env bash
# Invoked by deploy.yml on the existing Ubuntu production host, not on a laptop.
set -euo pipefail
umask 077

if [ "$#" -ne 6 ]; then
  echo 'Usage: deploy-production.sh PATH STAGE APP_VERSION AI_VERSION DOCKER_USER COMMIT' >&2
  exit 2
fi
deploy_path="$1"
stage="$2"
app_version="$3"
ai_version="$4"
docker_user="$5"
commit="$6"

test "$deploy_path" = /home/ubuntu/rxvita
[[ "$stage" =~ ^/home/ubuntu/rxvita/\.deploy/[0-9]+-[0-9]+$ ]]
[[ "$app_version" =~ ^build-[0-9]{8}-[1-9][0-9]*$ ]]
[[ "$ai_version" =~ ^build-[0-9]{8}-[1-9][0-9]*$ ]]
[[ "$docker_user" =~ ^[a-z0-9][a-z0-9_-]+$ ]]
[[ "$commit" =~ ^[0-9a-f]{40}$ ]]
cd "$deploy_path"

command -v flock >/dev/null
exec 9>.deploy.lock
flock -n 9 || { echo 'Another deployment holds the server lock.' >&2; exit 1; }
trap 'echo "Deployment failed; no automatic DB rollback. Private files: $stage" >&2' ERR

command -v rsync >/dev/null
command -v curl >/dev/null
command -v python3 >/dev/null
test -w .env
test -w docker-compose.yml
test -w nginx/default.conf
test -d frontend/dist
test -w frontend/dist
test -z "$(find frontend/dist -not -writable -print -quit)"
test "$(cat "$stage/source-sha")" = "$commit"

# Reuse the existing project identity; never accidentally create a second stack.
project="$(docker inspect fastapi --format '{{ index .Config.Labels "com.docker.compose.project" }}')"
workdir="$(docker inspect fastapi --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}')"
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]]
test "$workdir" = "$deploy_path"
export COMPOSE_PROJECT_NAME="$project"

compose() {
  docker compose --project-directory "$deploy_path" --env-file "$deploy_path/.env" \
    -f "$deploy_path/docker-compose.yml" "$@"
}
candidate() {
  docker compose --project-directory "$deploy_path" --env-file "$stage/.env" \
    -f "$stage/docker-compose.yml" "$@"
}

# Keep rendered configuration/errors private: they can contain secret values.
candidate config --format json > "$stage/config.json" 2> "$stage/config-errors.log" || {
  echo 'Candidate Compose config is invalid; inspect the private config-errors.log.' >&2
  exit 1
}
python3 - "$stage/config.json" "$app_version" "$ai_version" "$docker_user" <<'PY'
import json
import sys

with open(sys.argv[1]) as stream:
    services = json.load(stream)["services"]
app, ai, user = sys.argv[2:]
assert services["fastapi"]["image"] == f"{user}/rxvita:app-{app}", "Unexpected app image"
assert services["ai-worker"]["image"] == f"{user}/rxvita:ai-{ai}", "Unexpected AI image"
for key in ("MYSQL_ROOT_PASSWORD", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"):
    assert services["mysql"]["environment"].get(key), f"Missing production setting: {key}"
PY

mkdir -p "$stage/frontend" "$stage/backup"
tar -xzf "$stage/frontend.tar.gz" -C "$stage/frontend"
test -s "$stage/frontend/index.html"
test -s "$stage/frontend/sw.js"

# Back up before changing active config; this is NOT a database backup.
cp -p .env "$stage/backup/.env"
chmod 600 "$stage/backup/.env"
cp -p docker-compose.yml "$stage/backup/docker-compose.yml"
cp -p nginx/default.conf "$stage/backup/nginx.conf"
tar -czf "$stage/backup/frontend.tar.gz" -C frontend/dist .
compose images > "$stage/backup/images.txt"

app_image="$docker_user/rxvita:app-$app_version"
ai_image="$docker_user/rxvita:ai-$ai_version"
docker pull "$app_image"
docker pull "$ai_image"
for image in "$app_image" "$ai_image"; do
  revision="$(docker image inspect "$image" --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')"
  test "$revision" = "$commit" || { echo 'Image tag does not match the approved commit.' >&2; exit 1; }
done

# Test new HTTPS config against the existing network/certificate volumes BEFORE install.
compose run --rm --no-deps --entrypoint nginx \
  -v "$stage/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx -t

# rsync --inplace preserves the bind-mounted nginx file's inode.
# PROD_ENV_FILE replaces the server env just as the previous manual scp did.
rsync --inplace --chmod=F600 "$stage/.env" .env
rsync --inplace --chmod=F644 "$stage/docker-compose.yml" docker-compose.yml
rsync --inplace --chmod=F644 "$stage/nginx.conf" nginx/default.conf

# No `down`, no volume deletion, no image prune.
# Compose recreates changed services; DB/Redis can restart if their config changed.
# FastAPI's existing command runs Aerich upgrade. This may not be DB-reversible.
compose up -d --wait --wait-timeout 300

# Preserve old hashed assets for already-open clients; publish entrypoints last.
# Do not replace the dist directory inode while it is mounted by Nginx.
rsync -rlt --omit-dir-times --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  --exclude=index.html --exclude=sw.js "$stage/frontend/" frontend/dist/
install -m 644 "$stage/frontend/index.html" frontend/dist/.index.html.next
mv frontend/dist/.index.html.next frontend/dist/index.html
install -m 644 "$stage/frontend/sw.js" frontend/dist/.sw.js.next
mv frontend/dist/.sw.js.next frontend/dist/sw.js

compose exec -T nginx nginx -t
compose exec -T nginx nginx -s reload
for path in /api/openapi.json /login; do
  curl --fail --silent --show-error --retry 5 --retry-all-errors \
    --retry-delay 3 --connect-timeout 10 --max-time 30 \
    --resolve api.rxvita.p-e.kr:443:127.0.0.1 \
    "https://api.rxvita.p-e.kr$path" >/dev/null
done
compose ps
printf '%s\n' "$commit" > "$stage/deployed-sha"
echo "Deployment and basic HTTP checks finished: $app_version / $ai_version"
