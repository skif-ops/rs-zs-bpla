"""Pydantic schemas for ZS-BPLA station protocol v1.4."""
from __future__ import annotations

from enum import IntEnum
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

FEATURE_COUNT = 43

class TargetClass(IntEnum):
    UNKNOWN = 0
    PISTON_UAV = 1
    REACTIVE_UAV = 2
    ELECTRIC_UAV = 3
    ROAD_TRAFFIC = 10
    AIRCRAFT = 11
    HELICOPTER = 12
    GENERATOR = 13
    AGRICULTURAL = 14
    BIRDS = 15
    INSECTS = 16
    GUNFIRE = 17
    WIND = 18

class StationPosition(BaseModel):
    lat_e7: int
    lon_e7: int
    alt_dm: int
    pos_accuracy_m: float = 20.0
    altitude_source: Literal["gnss_msl", "configured_msl", "unknown"] = "gnss_msl"

    @property
    def lat(self) -> float: return self.lat_e7 / 1e7
    @property
    def lon(self) -> float: return self.lon_e7 / 1e7
    @property
    def alt_m(self) -> float: return self.alt_dm / 10.0

class GnssStatus(BaseModel):
    fix_type: int = 0
    satellites: int = 0
    hdop_x100: int = 9999
    pps_ok: bool = False
    expected_time_error_us: int = 1_000_000
    jam: bool = False
    spoof: bool = False

class Classification(BaseModel):
    class_id: int = int(TargetClass.UNKNOWN)
    label: str = "UNKNOWN"
    confidence_u8: int = Field(default=0, ge=0, le=255)
    unknown: bool = True

    @property
    def confidence(self) -> float: return self.confidence_u8 / 255.0

class DoaEstimate(BaseModel):
    azimuth_cdeg: int = 0
    elevation_cdeg: int = 0
    sigma_cdeg: int = 18000
    valid: bool = False

    @property
    def azimuth_deg(self) -> float: return self.azimuth_cdeg / 100.0
    @property
    def elevation_deg(self) -> float: return self.elevation_cdeg / 100.0
    @property
    def sigma_deg(self) -> float: return max(self.sigma_cdeg / 100.0, 0.1)

class TimeStatus(BaseModel):
    source: Literal["NONE", "GNSS_PPS", "HOLDOVER", "NTP", "NITZ"] = "NONE"
    quality: Literal["INVALID", "LOW", "MID", "HIGH"] = "INVALID"
    uncertainty_us: int = Field(default=1_000_000, ge=0)

    @property
    def tdoa_allowed(self) -> bool:
        return self.quality == "HIGH"

class SpatialEstimate(BaseModel):
    azimuth_cdeg: int = 0
    elevation_cdeg: int = 0
    sigma_azimuth_cdeg: int = 18000
    sigma_elevation_cdeg: int = 18000
    mic_health_mask: int = Field(default=0, ge=0, le=15)
    valid: bool = False

class PowerStatus(BaseModel):
    battery_pct: int = Field(default=0, ge=0, le=100)
    battery_mv: int = 0
    solar_mv: int = 0
    temperature_c10: int = 200

    @property
    def temperature_c(self) -> float: return self.temperature_c10 / 10.0

class RouteStatus(BaseModel):
    transport: Literal["LTE", "NB_IOT", "2G", "LORA", "BLE", "TEST"] = "TEST"
    hop_count: int = Field(default=0, ge=0, le=15)
    rssi_dbm: int | None = None
    snr_db10: int | None = None
    gateway_id: int | None = None

class AudioReference(BaseModel):
    local_slot: int = Field(default=0, ge=0, le=2)
    pre_ms: int = 30_000
    post_ms: int = 30_000
    codec: str = "pcm16_32k"

class DetectionMessage(BaseModel):
    schema_ver: int = 1
    station_id: int
    seq_no: int
    boot_id: int = 0
    event_id: int
    event_time_us: int
    station: StationPosition
    gnss: GnssStatus = Field(default_factory=GnssStatus)
    classification: Classification = Field(default_factory=Classification)
    features: list[float] = Field(default_factory=list)
    doa: DoaEstimate = Field(default_factory=DoaEstimate)
    spatial: SpatialEstimate = Field(default_factory=SpatialEstimate)
    time_status: TimeStatus = Field(default_factory=TimeStatus)
    power: PowerStatus = Field(default_factory=PowerStatus)
    route: RouteStatus = Field(default_factory=RouteStatus)
    audio_ref: AudioReference | None = None
    acoustic_snr_db: float | None = None
    detector_profile: Literal["piston", "reactive", "generic"] = "generic"
    sample_rate_hz: int = 32_000
    firmware_ver: str = "0.0.0"
    model_ver: str = "unknown"

    @field_validator("features")
    @classmethod
    def validate_features(cls, value: list[float]) -> list[float]:
        if value and len(value) != FEATURE_COUNT:
            raise ValueError(f"features must contain exactly {FEATURE_COUNT} values")
        return [float(v) for v in value]

class FeatureUpdateMessage(BaseModel):
    """MSG_FEATURES-equivalent update during one acoustic event/track."""

    schema_ver: int = 1
    station_id: int
    seq_no: int
    boot_id: int = 0
    event_id: int
    event_time_us: int
    features: list[float]
    acoustic_snr_db: float | None = None
    detector_profile: Literal["piston", "reactive", "generic"] = "generic"
    model_ver: str = "unknown"

    @field_validator("features")
    @classmethod
    def validate_feature_update(cls, value: list[float]) -> list[float]:
        if len(value) != FEATURE_COUNT:
            raise ValueError(f"features must contain exactly {FEATURE_COUNT} values")
        return [float(v) for v in value]


class OnlineTypeStatusMessage(BaseModel):
    station_id: int
    event_id: int
    elapsed_seconds: float = 0.0
    best_label: str = "UNKNOWN"
    confidence: float = 0.0
    margin: float = 0.0
    status: Literal["warming_up", "unknown", "provisional_candidate", "weak_candidate", "research_stable"] = "warming_up"
    type_lock_allowed: bool = False
    first_type_hypothesis_seconds: float | None = None
    research_stable_seconds: float | None = None
    model_version: str = "unknown"


class HeartbeatMessage(BaseModel):
    station_id: int
    time_us: int
    station: StationPosition
    gnss: GnssStatus = Field(default_factory=GnssStatus)
    power: PowerStatus = Field(default_factory=PowerStatus)
    route: RouteStatus = Field(default_factory=RouteStatus)
    firmware_ver: str = "0.0.0"
    model_ver: str = "unknown"
    hardware_rev: str = "EVT"
    self_test_ok: bool = True
    fault_flags: list[str] = Field(default_factory=list)

class SecurityEventMessage(BaseModel):
    schema_ver: int = 1
    station_id: int
    seq_no: int
    boot_id: int = 0
    event_id: int
    event_time_us: int
    station: StationPosition
    reason: Literal["case_open", "movement", "tilt", "power_loss", "other"]
    power: PowerStatus = Field(default_factory=PowerStatus)
    route: RouteStatus = Field(default_factory=RouteStatus)

class AudioRequest(BaseModel):
    event_id: int
    segment: Literal["pre", "post", "both", "range"] = "both"
    start_offset_ms: int | None = None
    duration_ms: int | None = None

class StationCommand(BaseModel):
    command_id: str
    station_id: int
    command: str
    payload: dict = Field(default_factory=dict)
    created_time_us: int

class TargetEstimate(BaseModel):
    lat: float | None = None
    lon: float | None = None
    alt_msl_m: float | None = None
    vx_east_mps: float | None = None
    vy_north_mps: float | None = None
    vz_up_mps: float | None = None
    speed_mps: float | None = None
    course_deg: float | None = None
    horizontal_error_m: float | None = None
    vertical_error_m: float | None = None
    localization_method: str = "insufficient_geometry"
    localization_mode: Literal["SINGLE_DOA", "TWO_STATION_COARSE", "HYBRID_3_2D5D", "FULL_3D", "CORRIDOR"] = "SINGLE_DOA"
    geometry_quality: Literal["invalid", "poor", "acceptable", "good"] = "invalid"
    quality: Literal["invalid", "low", "medium", "high"] = "invalid"

class SystemEvent(BaseModel):
    system_event_id: str
    event_type: Literal["AIR_WARNING", "AIR_ALERT", "SECURITY_EVENT"]
    created_time_us: int
    source_event_ids: list[int]
    source_station_ids: list[int]
    classification_label: str
    confidence: float
    stations_used: int
    target: TargetEstimate = Field(default_factory=TargetEstimate)
    route_summary: list[str] = Field(default_factory=list)
    status: Literal["active", "closed"] = "active"
