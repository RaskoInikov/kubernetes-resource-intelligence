"""Tests for versioned M1 contracts."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from pydantic import ValidationError

from kri.contracts import (
    ExperimentRecord,
    ExperimentState,
    LoadConfiguration,
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


def test_experiment_lifecycle_contract() -> None:
    started = datetime(2026, 10, 31, tzinfo=UTC)
    record = ExperimentRecord(
        experiment_id="exp-safe-1",
        workload_configuration=workload(),
        load_configuration=load(),
        start_timestamp=started,
        lifecycle_state=ExperimentState.RUNNING,
    )
    terminal = record.model_copy(
        update={
            "end_timestamp": started + timedelta(seconds=1),
            "lifecycle_state": ExperimentState.SUCCEEDED,
        }
    )

    assert record.end_timestamp is None
    assert terminal.lifecycle_state is ExperimentState.SUCCEEDED


@pytest.mark.parametrize(
    "values",
    [
        {"experiment_id": "NOT_SAFE"},
        {"start_timestamp": datetime(2026, 10, 31)},
        {"end_timestamp": datetime(2026, 10, 31, tzinfo=UTC)},
        {"lifecycle_state": "failed", "end_timestamp": None},
        {
            "lifecycle_state": "failed",
            "end_timestamp": datetime(2026, 10, 30, tzinfo=UTC),
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
