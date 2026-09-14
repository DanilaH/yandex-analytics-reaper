from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from yandex_analytics_reaper.durable_archive import (
    DurableArchiveError,
    build_archive_manifest,
    checksum_line,
    extract_verified_member,
    load_archive_manifest,
    load_archive_request,
    validate_request_catalog,
    verify_archive,
    write_manifest_create_only,
)


def _build(args: argparse.Namespace) -> None:
    request = load_archive_request(Path(args.request))
    manifest = build_archive_manifest(request, Path(args.artifact))
    write_manifest_create_only(manifest, Path(args.output))
    if args.checksum_output is not None:
        checksum_path = Path(args.checksum_output)
        checksum_path.parent.mkdir(parents=True, exist_ok=True)
        payload = checksum_line(manifest)
        try:
            with checksum_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
        except FileExistsError:
            if checksum_path.read_text(encoding="utf-8") != payload:
                raise DurableArchiveError(
                    f"refusing to replace different checksum file: {checksum_path}"
                ) from None
    print(manifest.model_dump_json(indent=2))


def _verify(args: argparse.Namespace) -> None:
    manifest = load_archive_manifest(Path(args.manifest))
    request = load_archive_request(Path(args.request)) if args.request is not None else None
    result = verify_archive(manifest, Path(args.artifact), request=request)
    print(result.model_dump_json(indent=2))


def _extract(args: argparse.Namespace) -> None:
    manifest = load_archive_manifest(Path(args.manifest))
    member = extract_verified_member(
        manifest,
        Path(args.artifact),
        member_path=args.member,
        output_path=Path(args.output),
    )
    print(member.model_dump_json(indent=2))


def _validate_catalog(args: argparse.Namespace) -> None:
    paths = tuple(Path(value) for value in args.request)
    result = validate_request_catalog(paths)
    print(result.model_dump_json(indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yandex-reaper-archive",
        description=(
            "Build, verify and extract hash-bound durable copies of ephemeral "
            "CI evidence artifacts."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate_catalog = sub.add_parser(
        "validate-catalog",
        help="Fail before side effects when committed archive requests collide.",
    )
    validate_catalog.add_argument(
        "request",
        nargs="+",
        help="One or more durable-evidence-archive-request-v1 JSON declarations.",
    )
    validate_catalog.set_defaults(handler=_validate_catalog)

    build = sub.add_parser(
        "build",
        help="Verify one downloaded Actions artifact and create its durable archive manifest.",
    )
    build.add_argument("request", help="durable-evidence-archive-request-v1 JSON declaration.")
    build.add_argument("artifact", help="Downloaded GitHub Actions artifact ZIP.")
    build.add_argument("output", help="Create-only output path for the archive manifest JSON.")
    build.add_argument(
        "--checksum-output",
        help="Optional create-only sha256sum-compatible checksum output path.",
    )
    build.set_defaults(handler=_build)

    verify = sub.add_parser(
        "verify",
        help="Verify the wrapper artifact, member inventory and canonical manifest content hash.",
    )
    verify.add_argument("manifest", help="durable-evidence-archive-v1 manifest JSON.")
    verify.add_argument("artifact", help="Archived Actions artifact ZIP.")
    verify.add_argument(
        "--request",
        help="Optional committed request that the manifest must match exactly.",
    )
    verify.set_defaults(handler=_verify)

    extract = sub.add_parser(
        "extract",
        help="Verify the wrapper, then extract one exact hash-bound member for offline reuse.",
    )
    extract.add_argument("manifest", help="durable-evidence-archive-v1 manifest JSON.")
    extract.add_argument("artifact", help="Archived Actions artifact ZIP.")
    extract.add_argument("member", help="Exact ZIP member path recorded in the manifest.")
    extract.add_argument("output", help="Output path for the verified member bytes.")
    extract.set_defaults(handler=_extract)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        handler = args.handler
        handler(args)
    except (DurableArchiveError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
