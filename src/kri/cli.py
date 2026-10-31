"""Command-line interface for explicitly invoked M1 workload operations."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from kri.config import load_settings
from kri.contracts import LoadConfiguration, WorkloadConfiguration, WorkloadMode
from kri.workload import ExperimentStore, KubectlClient, WorkloadController


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kri-workload")
    subparsers = parser.add_subparsers(dest="command", required=True)

    deploy = subparsers.add_parser("deploy", help="apply the application")
    _add_workload_arguments(deploy)

    subparsers.add_parser("delete", help="delete only the application")

    start = subparsers.add_parser("start-load", help="create an independent load Job")
    _add_workload_arguments(start)
    start.add_argument(
        "--mode", choices=[mode.value for mode in WorkloadMode], required=True
    )
    start.add_argument("--concurrency", type=int, required=True)
    start.add_argument("--request-rate", type=float, required=True)
    start.add_argument("--duration-seconds", type=int, required=True)
    start.add_argument("--experiment-id")

    stop = subparsers.add_parser("stop-load", help="delete one load Job")
    stop.add_argument("experiment_id")

    status = subparsers.add_parser("status", help="reconcile one experiment record")
    status.add_argument("experiment_id")
    return parser


def _add_workload_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cpu-request", required=True)
    parser.add_argument("--cpu-limit", required=True)
    parser.add_argument("--memory-request", required=True)
    parser.add_argument("--memory-limit", required=True)
    parser.add_argument("--replicas", type=int, required=True)


def _workload(arguments: argparse.Namespace) -> WorkloadConfiguration:
    return WorkloadConfiguration(
        cpu_request=arguments.cpu_request,
        cpu_limit=arguments.cpu_limit,
        memory_request=arguments.memory_request,
        memory_limit=arguments.memory_limit,
        replicas=arguments.replicas,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run an explicitly selected workload lifecycle operation."""

    arguments = _parser().parse_args(argv)
    settings = load_settings()
    controller = WorkloadController(
        KubectlClient(settings.k8s_context, settings.k8s_namespace),
        ExperimentStore(Path("results/experiments")),
        settings.workload_image,
    )

    if arguments.command == "deploy":
        controller.deploy_application(_workload(arguments))
        return 0
    if arguments.command == "delete":
        controller.delete_application()
        return 0
    if arguments.command == "start-load":
        record = controller.start_load(
            _workload(arguments),
            LoadConfiguration(
                workload_mode=arguments.mode,
                concurrency=arguments.concurrency,
                request_rate=arguments.request_rate,
                duration_seconds=arguments.duration_seconds,
            ),
            arguments.experiment_id,
        )
    elif arguments.command == "stop-load":
        record = controller.stop_load(arguments.experiment_id)
    else:
        record = controller.sync_load(arguments.experiment_id)
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0
