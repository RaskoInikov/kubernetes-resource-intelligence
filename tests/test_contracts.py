"""Tests for versioned M1 contracts."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from pydantic import ValidationError

from kri.contracts import (
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
    LoadExecutionSummary,
    WorkloadConfiguration,
    WorkloadMode,
)


def workload() -> WorkloadConfiguration:
    return WorkloadConfiguration(
        cpu_request="250m",
        cpu_limit="1",
        memory_request="64Mi",
        memory_limit="1Gi",
        replicas=2,
    )


def load() -> LoadConfiguration:
    return LoadConfiguration(
        workload_mode=WorkloadMode.MIXED,
        concurrency=4,
        request_rate=10.5,
        duration_seconds=30,
    )


def load_summary(**updates: object) -> LoadExecutionSummary:
    values: dict[str, object] = {
        "execution_status": "completed",
        "execution_failure_reason": None,
        "exit_code": 0,
        "requests_started": 12,
        "requests_completed": 12,
        "requests_succeeded": 10,
        "request_failures": 1,
        "request_timeouts": 1,
        "stuck_workers": 0,
    }
    values.update(updates)
    return LoadExecutionSummary.model_validate(values)


def test_valid_contracts_are_versioned_and_immutable() -> None:
    configuration = workload()

    assert configuration.schema_version == "1.0"
    assert load().workload_mode is WorkloadMode.MIXED
    with pytest.raises(ValidationError):
        cast(Any, configuration).replicas = 3


@pytest.mark.parametrize(
    "values",
    [
        {"cpu_request": "2", "cpu_limit": "1"},
        {"cpu_request": "0", "cpu_limit": "1"},
        {"cpu_request": "zero", "cpu_limit": "1"},
        {"memory_request": "2Gi", "memory_limit": "512Mi"},
        {"memory_request": "100MB", "memory_limit": "1Gi"},
        {"replicas": 0},
    ],
)
def test_invalid_workload_configuration_is_rejected(values: dict[str, object]) -> None:
    data: dict[str, object] = {
        "cpu_request": "250m",
        "cpu_limit": "1",
        "memory_request": "64Mi",
        "memory_limit": "1Gi",
        "replicas": 2,
    }
    data.update(values)

    with pytest.raises(ValidationError):
        WorkloadConfiguration.model_validate(data)


@pytest.mark.parametrize(
    "values",
    [
        {"workload_mode": "incident"},
        {"concurrency": 0},
        {"request_rate": 0},
        {"duration_seconds": 3601},
    ],
)
def test_invalid_load_configuration_is_rejected(values: dict[str, object]) -> None:
    data: dict[str, object] = {
        "workload_mode": "cpu",
        "concurrency": 1,
        "request_rate": 1,
        "duration_seconds": 10,
    }
    data.update(values)

    with pytest.raises(ValidationError):
        LoadConfiguration.model_validate(data)


@pytest.mark.parametrize(
    "updates",
    [
        {"requests_completed": 11},
        {"requests_started": 13},
        {"exit_code": 4},
        {"execution_failure_reason": "stuck_worker"},
        {"stuck_workers": 1, "requests_started": 13},
        {
            "execution_status": "failed",
            "execution_failure_reason": "stuck_worker",
            "stuck_workers": 1,
            "requests_started": 13,
            "exit_code": 0,
        },
    ],
)
def test_invalid_load_execution_summary_is_rejected(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        load_summary(**updates)


def test_stuck_worker_is_an_execution_failure_with_preserved_client_outcomes() -> None:
    summary = load_summary(
        execution_status="failed",
        execution_failure_reason="stuck_worker",
        exit_code=4,
        requests_started=13,
        stuck_workers=1,
    )

    assert summary.exit_code == 4
    assert summary.request_failures == 1
    assert summary.request_timeouts == 1


def test_experiment_lifecycle_contract() -> None:
    started = datetime(2026, 10, 31, tzinfo=UTC)
    record = ExperimentRecord(
        experiment_id="exp-safe-1",
        workload_configuration=workload(),
        load_configuration=load(),
        start_timestamp=started,
        lifecycle_state=ExperimentState.RUNNING,
    )
    terminal = ExperimentRecord.model_validate(
        {
            **record.model_dump(),
            "job_uid": "job-uid-1",
            "job_start_timestamp": started,
            "end_timestamp": started + timedelta(seconds=1),
            "lifecycle_state": ExperimentState.SUCCEEDED,
            "termination_reason": "Complete",
            "termination_source": "kubernetes",
            "load_summary": load_summary(),
        }
    )

    assert record.end_timestamp is None
    assert terminal.lifecycle_state is ExperimentState.SUCCEEDED

    legacy = ExperimentRecord.model_validate(
        {
            **terminal.model_dump(),
            "schema_version": "1.0",
            "termination_reason": None,
            "termination_source": None,
            "load_summary": None,
        }
    )
    assert legacy.schema_version == "1.0"


def test_experiment_load_summary_lifecycle_guards() -> None:
    started = datetime(2026, 10, 31, tzinfo=UTC)
    completed = load_summary()
    failed = load_summary(
        execution_status="failed",
        execution_failure_reason="stuck_worker",
        exit_code=4,
        requests_started=13,
        stuck_workers=1,
    )
    base: dict[str, object] = {
        "experiment_id": "exp-summary",
        "workload_configuration": workload(),
        "load_configuration": load(),
        "start_timestamp": started,
        "job_uid": "job-uid",
        "job_start_timestamp": started,
        "end_timestamp": started + timedelta(seconds=30),
        "termination_reason": "Complete",
        "termination_source": "kubernetes",
    }

    invalid = (
        {
            **base,
            "schema_version": "1.1",
            "lifecycle_state": "succeeded",
            "load_summary": completed,
        },
        {
            **base,
            "lifecycle_state": "running",
            "end_timestamp": None,
            "termination_reason": None,
            "termination_source": None,
            "load_summary": completed,
        },
        {**base, "lifecycle_state": "succeeded", "load_summary": None},
        {**base, "lifecycle_state": "succeeded", "load_summary": failed},
        {**base, "lifecycle_state": "failed", "load_summary": completed},
    )
    for value in invalid:
        with pytest.raises(ValidationError):
            ExperimentRecord.model_validate(value)


@pytest.mark.parametrize(
    "values",
    [
        {"experiment_id": "NOT_SAFE"},
        {"start_timestamp": datetime(2026, 10, 31)},
        {"job_uid": " "},
        {"job_start_timestamp": datetime(2026, 10, 31)},
        {"end_timestamp": datetime(2026, 10, 31, tzinfo=UTC)},
        {"termination_reason": "Complete"},
        {"lifecycle_state": "failed", "end_timestamp": None},
        {
            "lifecycle_state": "failed",
            "end_timestamp": datetime(2026, 11, 1, tzinfo=UTC),
            "job_uid": "job-uid-1",
            "job_start_timestamp": datetime(2026, 10, 31, tzinfo=UTC),
        },
        {
            "lifecycle_state": "failed",
            "end_timestamp": datetime(2026, 11, 1, tzinfo=UTC),
            "termination_reason": "Failed",
            "termination_source": "kubernetes",
        },
        {
            "lifecycle_state": "failed",
            "end_timestamp": datetime(2026, 10, 30, tzinfo=UTC),
        },
        {
            "lifecycle_state": "failed",
            "job_uid": "job-uid-1",
            "job_start_timestamp": datetime(2026, 11, 2, tzinfo=UTC),
            "end_timestamp": datetime(2026, 11, 1, tzinfo=UTC),
            "termination_reason": "Failed",
            "termination_source": "kubernetes",
        },
    ],
)
def test_invalid_experiment_record_is_rejected(values: dict[str, object]) -> None:
    data: dict[str, object] = {
        "experiment_id": "exp-safe-1",
        "workload_configuration": workload(),
        "load_configuration": load(),
        "start_timestamp": datetime(2026, 10, 31, tzinfo=UTC),
        "lifecycle_state": "running",
    }
    data.update(values)

    with pytest.raises(ValidationError):
        ExperimentRecord.model_validate(data)
