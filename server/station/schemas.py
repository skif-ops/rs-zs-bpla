"""Pydantic schemas for ZS-BPLA station protocol v1.2."""
from __future__ import annotations

from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

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


class AcousticFamily(IntEnum):
    UNKNOWN = 0
    PROP_PISTON = 1
    ROTOR_ELECTRIC = 2
    TURBINE_JET = 3


class SpecificType(IntEnum):
    UNKNOWN = 0
    LUTYI = 1
    FP1 = 2
    FP2 = 3
    OTHER = 254


DecisionStatus = Literal["UNKNOWN", "CANDIDATE", "PROVISIONAL", "STABLE", "UNSUPPORTED"]
MotionHint = Literal["UNKNOWN", "APPROACH", "PASSING", "RECEDING"]


class StationPosition(BaseModel):
    lat_e7: int
    lon_e7: int
    alt_dm: int
    pos_accuracy_m: float = 20.0
    altitude_source: Literal["gnss_msl", "configured_msl", "unknown"] = "gnss_msl"

    @property
    def lat(self) -> float:
        return self.lat_e7 / 1e7

    @property
    def lon(self) -> float:
        return self.lon_e7 / 1e7

    @property
    def alt_m(self) -> float:
        return self.alt_dm / 10.0


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
    def confidence(self) -> float:
        return self.confidence_u8 / 255.0


class HierarchicalClassification(BaseModel):
    family_id: int = int(AcousticFamily.UNKNOWN)
    family_label: str = "UNKNOWN"
    family_confidence_u8: int = Field(default=0, ge=0, le=255)
    family_status: DecisionStatus = "UNKNOWN"
    type_id: int = int(SpecificType.UNKNOWN)
    type_label: str = "UNKNOWN"
    type_confidence_u8: int = Field(default=0, ge=0, le=255)
    type_status: DecisionStatus = "UNKNOWN"

    @property
    def family_confidence(self) -> float:
        return self.family_confidence_u8 / 255.0

    @property
    def type_confidence(self) -> float:
        return self.type_confidence_u8 / 255.0


class SingleStationEstimate(BaseModel):
    height_dm: int = 0
    height_sigma_dm: int = Field(default=0, ge=0)
    speed_dmps: int = Field(default=0, ge=0)
    speed_sigma_dmps: int = Field(default=0, ge=0)
    confidence_u8: int = Field(default=0, ge=0, le=255)
    height_valid: bool = False
    speed_valid: bool = False
    motion_hint: MotionHint = "UNKNOWN"

    @property
    def height_m(self) -> float:
        return self.height_dm / 10.0

    @property
    def height_sigma_m(self) -> float:
        return self.height_sigma_dm / 10.0

    @property
    def speed_mps(self) -> float:
        return self.speed_dmps / 10.0

    @property
    def speed_sigma_mps(self) -> float:
        return self.speed_sigma_dmps / 10.0

    @property
    def confidence(self) -> float:
        return self.confidence_u8 / 255.0


class DoaEstimate(BaseModel):
    azimuth_cdeg: int = 0
    elevation_cdeg: int = 0
    sigma_cdeg: int = 18000
    valid: bool = False

    @property
    def azimuth_deg(self) -> float:
        return self.azimuth_cdeg / 100.0

    @property
    def elevation_deg(self) -> float:
        return self.elevation_cdeg / 100.0

    @property
    def sigma_deg(self) -> float:
        return max(self.sigma_cdeg / 100.0, 0.1)


class PowerStatus(BaseModel):
    battery_pct: int = Field(default=0, ge=0, le=100)
    battery_mv: int = 0
    solar_mv: int = 0
    temperature_c10: int = 200

    @property
    def temperature_c(self) -> float:
        return self.temperature_c10 / 10.0


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
    hierarchy: HierarchicalClassification = Field(default_factory=HierarchicalClassification)
    single_station_estimate: SingleStationEstimate = Field(default_factory=SingleStationEstimate)
    features: list[float] = Field(default_factory=list)
    doa: DoaEstimate = Field(default_factory=DoaEstimate)
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
