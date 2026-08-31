import argparse
import asyncio
from contextlib import AsyncExitStack
from pathlib import Path

import yaml
from qdrant_client import AsyncQdrantClient
from tortoise import Tortoise

from ai_worker.core.config import Config
from ai_worker.evaluation.chat_evaluation_executor import (
    ChatCoreEvaluationExecutor,
)
from ai_worker.evaluation.chat_evaluator import (
    ChatEvaluator,
    render_chat_evaluation_markdown,
)
from ai_worker.schemas.chat_evaluation import (
    ChatEvaluationManifest,
    ChatEvaluationReport,
)
from ai_worker.services.medication_chat_core_service import (
    build_medication_chat_core_service,
)
from app.core.db.databases import TORTOISE_ORM


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("약·영양제 Chat Core 대표 질문을 순차 실행하고 계약 비교 보고서를 생성합니다.")
    )
    parser.add_argument("--evaluation-file", type=Path, required=True)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--care-episode-id", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.user_id < 1:
        parser.error("--user-id는 1 이상이어야 합니다.")
    if args.care_episode_id is not None and args.care_episode_id < 1:
        parser.error("--care-episode-id는 1 이상이어야 합니다.")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds는 0보다 커야 합니다.")
    if args.output.suffix.casefold() not in {".json", ".md"}:
        parser.error("--output 확장자는 .json 또는 .md여야 합니다.")
    return args


def load_evaluation_manifest(path: Path) -> ChatEvaluationManifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ChatEvaluationManifest.model_validate(raw)


def write_report(
    report: ChatEvaluationReport,
    output_path: Path,
) -> None:
    suffix = output_path.suffix.casefold()
    if suffix == ".json":
        content = report.model_dump_json(indent=2)
    elif suffix == ".md":
        content = render_chat_evaluation_markdown(report)
    else:
        raise ValueError("평가 보고서 확장자는 json 또는 md여야 합니다.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> ChatEvaluationReport:
    resolved_settings = settings or Config()
    manifest = load_evaluation_manifest(args.evaluation_file)
    async with AsyncExitStack() as stack:
        await Tortoise.init(config=TORTOISE_ORM)
        stack.push_async_callback(Tortoise.close_connections)
        qdrant_client = AsyncQdrantClient(
            url=resolved_settings.QDRANT_URL,
            timeout=resolved_settings.QDRANT_TIMEOUT_SECONDS,
        )
        stack.push_async_callback(qdrant_client.close)
        core_service = build_medication_chat_core_service(
            settings=resolved_settings,
            qdrant_client=qdrant_client,
        )
        stack.push_async_callback(core_service.tracer.aclose)
        executor = ChatCoreEvaluationExecutor(
            core_service=core_service,
            tracer=core_service.tracer,
            user_id=args.user_id,
            care_episode_id=args.care_episode_id,
            timeout_seconds=args.timeout_seconds,
        )
        report = await ChatEvaluator(executor=executor).evaluate(manifest)
        write_report(report, args.output)
        return report


def exit_code_for(report: ChatEvaluationReport) -> int:
    return 0 if report.passed else 2


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_cli(args=args))
    print(f"평가 완료: {report.passed_count}/{report.query_count} 통과, 보고서={args.output}")
    raise SystemExit(exit_code_for(report))


if __name__ == "__main__":
    main()
