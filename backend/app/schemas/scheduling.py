"""Versioned contract for appliance schedule previews."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SchedulingContractModel(BaseModel):
    """Base settings shared by scheduling v1 request and response models."""

    model_config = ConfigDict(extra="forbid")


class BaselineSource(str, Enum):
    """Permitted provenance for a fixed demand baseline."""

    INDEPENDENTLY_MEASURED = "independently_measured"
    SYNTHETIC = "synthetic"


class SchedulingStatus(str, Enum):
    """Planning status for validation and optimization outcomes."""

    BLOCKED = "blocked"
    NOT_EVALUATED = "not_evaluated"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"


class TariffResolutionStatus(str, Enum):
    """Whether an owned, current tariff can be used by a future planner."""

    CONFIGURED = "configured"
    MISSING = "missing"
    ILLUSTRATIVE = "illustrative"
    OUTSIDE_EFFECTIVE_DATES = "outside_effective_dates"
    MISSING_RATES = "missing_rates"


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Datetime values must include an explicit UTC offset")
    return value


class BaselineIntervalV1(SchedulingContractModel):
    """One fixed interval of non-task baseline demand, measured in kW."""

    interval_start: datetime = Field(
        description="Inclusive start instant of this interval; RFC 3339 with UTC offset."
    )
    demand_kw: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Fixed non-task average demand during this interval, in kW.",
    )

    @field_validator("interval_start")
    @classmethod
    def require_aware_interval_start(cls, value: datetime) -> datetime:
        return _require_aware(value)


class FixedBaselineProfileV1(SchedulingContractModel):
    """Explicit independent or synthetic baseline, never raw net meter demand."""

    source: BaselineSource
    profile_id: str = Field(min_length=1, max_length=80)
    measurement_method: Literal["submeter", "validated_disaggregation"] | None = None
    scenario_id: str | None = Field(default=None, min_length=1, max_length=80)
    includes_scheduled_tasks: Literal[False] = False
    intervals: list[BaselineIntervalV1] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_source_provenance(self) -> "FixedBaselineProfileV1":
        if self.source == BaselineSource.SYNTHETIC:
            if self.scenario_id is None:
                raise ValueError("Synthetic baselines require a scenario_id")
            if self.measurement_method is not None:
                raise ValueError("Synthetic baselines cannot declare a measurement_method")
        elif self.measurement_method is None:
            raise ValueError(
                "Independently measured baselines require a supported measurement_method"
            )
        return self


class ApplianceTaskV1(SchedulingContractModel):
    """One non-interruptible task with explicit timing, units, and obligation."""

    task_id: str = Field(min_length=1, max_length=80)
    appliance: str = Field(min_length=1, max_length=100)
    rated_power_kw: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Rated constant task power in kW; provide this or energy_kwh.",
    )
    energy_kwh: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Task energy demand in kWh; provide this or rated_power_kw.",
    )
    duration_minutes: int = Field(
        gt=0,
        le=1440,
        description="Fixed, non-interruptible task duration in minutes.",
    )
    earliest_start: datetime = Field(
        description="Earliest allowed task start; RFC 3339 with an explicit UTC offset."
    )
    deadline: datetime = Field(
        description="Latest task finish time; the task must complete by this instant."
    )
    preferred_start: datetime | None = Field(
        default=None,
        description="Optional preferred start instant; it must fit the complete task.",
    )
    mandatory: bool = Field(
        description="Whether omission is prohibited by the user's task requirement."
    )
    omission_penalty_aud: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description=(
            "AUD objective penalty when an optional task is omitted; required exactly "
            "when mandatory is false."
        ),
    )

    @field_validator("earliest_start", "deadline", "preferred_start")
    @classmethod
    def require_aware_task_times(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_aware(value)

    @model_validator(mode="after")
    def require_exactly_one_energy_rating(self) -> "ApplianceTaskV1":
        if (self.rated_power_kw is None) == (self.energy_kwh is None):
            raise ValueError("Provide exactly one of rated_power_kw or energy_kwh")
        if self.deadline.astimezone(timezone.utc) <= self.earliest_start.astimezone(timezone.utc):
            raise ValueError("deadline must be later than earliest_start")
        if self.mandatory and self.omission_penalty_aud is not None:
            raise ValueError("Required tasks cannot define an omission_penalty_aud")
        return self


_SCHEDULING_REQUEST_EXAMPLE = {
    "schema_version": "1.0",
    "meter_id": 42,
    "tariff_id": 17,
    "scenario_id": "demo-water-heater",
    "interval_minutes": 30,
    "timezone": "Australia/Melbourne",
    "currency": "AUD",
    "preference_penalty_aud_per_interval": 0.01,
    "tasks": [
        {
            "task_id": "water-heater-1",
            "appliance": "Water heater",
            "rated_power_kw": 2.4,
            "duration_minutes": 60,
            "earliest_start": "2026-11-03T08:00:00+11:00",
            "deadline": "2026-11-03T10:00:00+11:00",
            "preferred_start": "2026-11-03T08:30:00+11:00",
            "mandatory": True,
        }
    ],
    "baseline_profile": {
        "source": "synthetic",
        "profile_id": "demo-water-heater-baseline-v1",
        "scenario_id": "demo-water-heater",
        "includes_scheduled_tasks": False,
        "intervals": [
            {
                "interval_start": f"2026-11-03T{hour:02d}:{minute:02d}:00+11:00",
                "demand_kw": 0.8,
            }
            for hour, minute in ((8, 0), (8, 30), (9, 0), (9, 30))
        ],
    },
}

_SCHEDULING_RESPONSE_EXAMPLE = {
    "schema_version": "1.0",
    "scenario_id": "demo-water-heater",
    "meter_id": 42,
    "status": "feasible",
    "tariff": {"tariff_id": 17, "status": "configured", "currency": "AUD"},
    "objective_breakdown": {
        "currency": "AUD",
        "baseline_energy_cost_aud": 0.448,
        "candidate_energy_cost_aud": 1.12,
        "reference_energy_cost_aud": 1.12,
        "energy_cost_delta_aud": 0.0,
        "preference_penalty_aud": 0.0,
        "omission_penalty_aud": 0.0,
        "total_objective_aud": 1.12,
        "reference_preference_penalty_aud": 0.0,
        "reference_omission_penalty_aud": 0.0,
        "reference_objective_aud": 1.12,
    },
    "candidate_schedule": {
        "status": "feasible",
        "method": "milp",
        "tasks": [
            {
                "task_id": "water-heater-1",
                "start": "2026-11-03T08:30:00+11:00",
                "end": "2026-11-03T09:30:00+11:00",
                "power_kw": 2.4,
                "energy_kwh": 2.4,
                "omitted": False,
            }
        ],
        "total_energy_kwh": 4.0,
        "total_cost_aud": 1.12,
    },
    "reference_schedule": {
        "status": "feasible",
        "method": "deterministic_greedy",
        "tasks": [
            {
                "task_id": "water-heater-1",
                "start": "2026-11-03T08:30:00+11:00",
                "end": "2026-11-03T09:30:00+11:00",
                "power_kw": 2.4,
                "energy_kwh": 2.4,
                "omitted": False,
            }
        ],
        "total_energy_kwh": 4.0,
        "total_cost_aud": 1.12,
    },
    "assumptions": [
        (
            "The fixed baseline excludes scheduled tasks; "
            "its energy and cost are included exactly once."
        ),
        "Task demand is constant fixed power for the full non-interruptible task duration.",
        (
            "Energy charges use the owned tariff's interval rates; "
            "daily supply and demand charges are excluded."
        ),
        "The candidate-minus-reference energy cost delta is not a household savings estimate.",
        "Optional tasks without an omission penalty are omitted under the no-savings treatment.",
        (
            "The deterministic greedy reference uses the same tasks, tariff, baseline, "
            "and power limits; it is not an optimum."
        ),
        "This endpoint returns a preview only and never executes or dispatches devices.",
        (
            "Baseline profile demo-water-heater-baseline-v1 is synthetic "
            "for scenario demo-water-heater."
        ),
        (
            "Preference cost is preference_penalty_aud_per_interval times the distance "
            "from preferred_start in scheduling intervals."
        ),
    ],
    "blockers": [],
}


class SchedulingRequestV1(SchedulingContractModel):
    """Stable request contract for scheduling previews."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [_SCHEDULING_REQUEST_EXAMPLE]},
    )

    schema_version: Literal["1.0"] = Field(
        description="Request contract version; use 1.0 for this route."
    )
    meter_id: int = Field(gt=0)
    tariff_id: int | None = Field(default=None, gt=0)
    scenario_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$",
    )
    interval_minutes: Literal[5, 15, 30, 60] = Field(
        description="Local interval-grid duration in minutes."
    )
    timezone: str = Field(
        min_length=1,
        max_length=64,
        description="IANA timezone for the meter's local scheduling calendar.",
    )
    currency: Literal["AUD"] = Field(description="All objective costs are denominated in AUD.")
    preference_penalty_aud_per_interval: float = Field(
        default=0.01,
        ge=0,
        allow_inf_nan=False,
        description=(
            "Configurable AUD penalty per scheduling interval between a task's actual and "
            "preferred start. Applies only when preferred_start is provided."
        ),
    )
    household_power_limit_kw: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Optional maximum total household demand in kW, including the baseline.",
    )
    grid_power_limit_kw: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="Optional maximum total demand in kW, including the baseline.",
    )
    tasks: list[ApplianceTaskV1] = Field(min_length=1, max_length=20)
    baseline_profile: FixedBaselineProfileV1

    @field_validator("timezone")
    @classmethod
    def validate_iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_time_grid_and_baseline(self) -> "SchedulingRequestV1":
        zone = ZoneInfo(self.timezone)
        step = timedelta(minutes=self.interval_minutes)
        step_seconds = step.total_seconds()

        if self.baseline_profile.source == BaselineSource.SYNTHETIC:
            if self.baseline_profile.scenario_id != self.scenario_id:
                raise ValueError(
                    "Synthetic baseline scenario_id must match the request scenario_id"
                )

        task_ids: set[str] = set()
        for task in self.tasks:
            if task.task_id in task_ids:
                raise ValueError("task_id values must be unique")
            task_ids.add(task.task_id)

            if task.duration_minutes % self.interval_minutes:
                raise ValueError("duration_minutes must be a multiple of interval_minutes")

            latest_start = task.deadline.astimezone(timezone.utc) - timedelta(
                minutes=task.duration_minutes
            )
            if latest_start < task.earliest_start.astimezone(timezone.utc):
                raise ValueError("Task duration does not fit within its available window")

            task_times = [task.earliest_start, task.deadline]
            if task.preferred_start is not None:
                task_times.append(task.preferred_start)

            for value in task_times:
                self._validate_local_time(value, zone, self.interval_minutes)

            if task.preferred_start is not None:
                preferred = task.preferred_start.astimezone(timezone.utc)
                earliest = task.earliest_start.astimezone(timezone.utc)
                if preferred < earliest or preferred > latest_start:
                    raise ValueError(
                        "preferred_start must allow the full task duration before deadline"
                    )

        intervals = self.baseline_profile.intervals
        utc_starts = [item.interval_start.astimezone(timezone.utc) for item in intervals]
        for item in intervals:
            self._validate_local_time(item.interval_start, zone, self.interval_minutes)

        if any(current <= previous for previous, current in zip(utc_starts, utc_starts[1:])):
            raise ValueError("Baseline intervals must be time-ordered without overlaps")
        for previous, current in zip(utc_starts, utc_starts[1:]):
            delta_seconds = (current - previous).total_seconds()
            if delta_seconds < step_seconds:
                raise ValueError("Baseline intervals cannot overlap")
            if delta_seconds > step_seconds:
                raise ValueError("Baseline intervals must be contiguous without gaps")

        first_start = utc_starts[0]
        final_end = utc_starts[-1] + step
        for task in self.tasks:
            if first_start > task.earliest_start.astimezone(
                timezone.utc
            ) or final_end < task.deadline.astimezone(timezone.utc):
                raise ValueError(
                    "Baseline profile must cover each task's complete scheduling window"
                )

        return self

    @staticmethod
    def _validate_local_time(value: datetime, zone: ZoneInfo, interval_minutes: int) -> None:
        local_value = value.astimezone(zone)
        if local_value.utcoffset() != value.utcoffset():
            raise ValueError("Datetime UTC offset does not match the requested timezone")
        if (
            local_value.second != 0
            or local_value.microsecond != 0
            or local_value.minute % interval_minutes != 0
        ):
            raise ValueError("Datetime must align to the requested interval grid")


class TariffResolutionV1(SchedulingContractModel):
    """Server-resolved tariff identity and provenance."""

    tariff_id: int | None = None
    status: TariffResolutionStatus
    currency: Literal["AUD"] = "AUD"


class ScheduledTaskV1(SchedulingContractModel):
    """Future schedule result item; no device command is implied."""

    task_id: str
    start: datetime | None
    end: datetime | None
    power_kw: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    energy_kwh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    omitted: bool = False

    @model_validator(mode="after")
    def validate_omission_times(self) -> "ScheduledTaskV1":
        if self.omitted and (self.start is not None or self.end is not None):
            raise ValueError("Omitted tasks cannot have start or end times")
        if not self.omitted and (self.start is None or self.end is None):
            raise ValueError("Scheduled tasks require start and end times")
        return self


class ScheduleV1(SchedulingContractModel):
    """A candidate schedule or deterministic greedy reference result."""

    status: Literal["feasible", "not_found"]
    method: Literal["milp", "deterministic_greedy"]
    reason: str | None = None
    tasks: list[ScheduledTaskV1]
    total_energy_kwh: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    total_cost_aud: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ObjectiveBreakdownV1(SchedulingContractModel):
    """Transparent energy, preference, and omission objective components in AUD."""

    currency: Literal["AUD"] = "AUD"
    baseline_energy_cost_aud: float | None = None
    candidate_energy_cost_aud: float | None = None
    reference_energy_cost_aud: float | None = None
    energy_cost_delta_aud: float | None = None
    preference_penalty_aud: float | None = None
    omission_penalty_aud: float | None = None
    total_objective_aud: float | None = None
    reference_preference_penalty_aud: float | None = None
    reference_omission_penalty_aud: float | None = None
    reference_objective_aud: float | None = None


class SchedulingResponseV1(SchedulingContractModel):
    """Schedule preview result with explicit unavailable and feasibility states."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [_SCHEDULING_RESPONSE_EXAMPLE]},
    )

    schema_version: Literal["1.0"]
    scenario_id: str
    meter_id: int
    status: SchedulingStatus
    tariff: TariffResolutionV1
    objective_breakdown: ObjectiveBreakdownV1 | None = None
    candidate_schedule: ScheduleV1 | None = None
    reference_schedule: ScheduleV1 | None = None
    assumptions: list[str]
    blockers: list[str]
