"""Verify the real M10 HTTP workflow using one retained observation."""

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify M10 over HTTP from retained M3/M4 evidence"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--observation-id", required=True)
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(
            f"{method} {path} returned {error.code}: {detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"{method} {path} failed: {error.reason}") from error


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    args = parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)

    health = request_json(args.url, "GET", "/healthz")
    openapi = request_json(args.url, "GET", "/openapi.json")
    observation_summary = request_json(
        args.url,
        "GET",
        f"/api/v1/observations/{args.observation_id}/summary",
    )
    observation = request_json(
        args.url, "GET", f"/api/v1/observations/{args.observation_id}"
    )
    analysis = request_json(
        args.url,
        "POST",
        "/api/v1/analyses",
        {"observation_id": args.observation_id, "analysis_id": args.analysis_id},
    )
    evidence = request_json(
        args.url,
        "POST",
        "/api/v1/rag/evidence",
        {"analysis": analysis, "limit_per_query": 5},
    )
    created_package = request_json(
        args.url,
        "POST",
        "/api/v1/llm-inputs",
        {
            "analysis": analysis,
            "evidence": evidence,
            "package_id": args.package_id,
        },
    )
    loaded_package = request_json(
        args.url, "GET", f"/api/v1/llm-inputs/{args.package_id}"
    )
    package_summary = request_json(
        args.url, "GET", f"/api/v1/llm-inputs/{args.package_id}/summary"
    )

    required_paths = {
        "/api/v1/observations/{observation_id}",
        "/api/v1/observations/{observation_id}/summary",
        "/api/v1/analyses",
        "/api/v1/rag/evidence",
        "/api/v1/llm-inputs",
        "/api/v1/llm-inputs/{package_id}",
        "/api/v1/llm-inputs/{package_id}/summary",
    }
    require(health.get("status") == "ok", "health endpoint did not return ok")
    require(
        required_paths <= set(openapi.get("paths", {})),
        "OpenAPI is missing a pipeline route",
    )
    require(
        observation_summary["observation_id"] == args.observation_id,
        "observation summary identity changed",
    )
    require(
        observation["observation_id"] == args.observation_id,
        "loaded observation identity changed",
    )
    source_digest = observation["provenance"]["source_digest_sha256"]
    require(
        observation_summary["quality_status"] == "complete",
        "retained real observation is not complete",
    )
    require(analysis["analysis_id"] == args.analysis_id, "analysis ID changed")
    require(
        analysis["observation_id"] == args.observation_id,
        "analysis references the wrong observation",
    )
    require(
        analysis["provenance"]["observation_source_digest_sha256"] == source_digest,
        "analysis lost observation digest provenance",
    )
    require(evidence["analysis_id"] == args.analysis_id, "M8 analysis ID changed")
    require(bool(evidence["bundles"]), "M8 produced no evidence bundles")
    require(
        all(bundle["retrieval"]["hits"] for bundle in evidence["bundles"]),
        "an M8 query returned no verified evidence",
    )
    all_hits_verified = all(
        hit["chunk"]["verification_status"] == "verified"
        for bundle in evidence["bundles"]
        for hit in bundle["retrieval"]["hits"]
    )
    require(all_hits_verified, "M8 returned unverified knowledge")
    require(created_package == loaded_package, "persisted package did not round-trip")
    require(
        created_package["package_id"] == args.package_id,
        "created package ID changed",
    )
    require(
        created_package["analysis_id"] == args.analysis_id,
        "M9 package references the wrong analysis",
    )
    require(
        package_summary["package_id"] == args.package_id,
        "package summary identity changed",
    )
    require(
        package_summary["retrieval_status"] == "retrieved",
        "M9 package does not report retrieved evidence",
    )

    responses = {
        "observation-summary.json": observation_summary,
        "analysis.json": analysis,
        "operational-evidence.json": evidence,
        "llm-input.json": created_package,
        "llm-input-summary.json": package_summary,
    }
    for name, value in responses.items():
        write_json(args.output_directory / name, value)

    result = {
        "api": {
            "url": args.url,
            "version": openapi["info"]["version"],
            "health": health["status"],
            "required_pipeline_routes_present": True,
        },
        "observation": {
            "observation_id": args.observation_id,
            "quality_status": observation_summary["quality_status"],
            "normalized_series_count": observation_summary["normalized_series_count"],
            "sample_count": observation_summary["sample_count"],
            "source_digest_sha256": source_digest,
        },
        "analysis": {
            "analysis_id": args.analysis_id,
            "sufficiency": analysis["sufficiency"],
            "statistic_count": len(analysis["statistics"]),
            "condition_count": len(analysis["conditions"]),
            "recommendation_count": len(analysis["recommendations"]),
            "uncertainty_count": len(analysis["risks_and_uncertainties"]),
        },
        "retrieval": {
            "bundle_count": len(evidence["bundles"]),
            "hit_counts": [
                len(bundle["retrieval"]["hits"]) for bundle in evidence["bundles"]
            ],
            "all_hits_verified": all_hits_verified,
        },
        "llm_input": {
            "package_id": args.package_id,
            "retrieval_status": package_summary["retrieval_status"],
            "query_count": package_summary["query_count"],
            "hit_reference_count": package_summary["hit_reference_count"],
            "excerpt_count": package_summary["excerpt_count"],
            "package_sha256": package_summary["package_sha256"],
            "round_trip_exact": created_package == loaded_package,
        },
    }
    write_json(args.output_directory / "verification-summary.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
