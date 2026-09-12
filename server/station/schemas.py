"""Pydantic schemas for ZS-BPLA station protocol v1.5."""
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
PositionSource = Literal["gnss_live", "configured_install"]
PositionTrustState = Literal[
    "UNCONFIGURED",
    "CONFIGURED_OK",
    "CONFIGURED_WARN",
    "CONFIGURED_SUSPECT",
    "REVALIDATION_REQUIRED",
]
TimeTrustState = Literal[
    "UNKNOWN",
    "GNSS_TIME_TRUSTED",
    "HOLDOVER",
    "GNSS_TIME_SUSPECT",
    "UNSYNCED",
]


class StationPosition(BaseModel):
    lat_e7: int
    lon_e7: int
    alt_dm: int
    pos_accuracy_m: float = 20.0
    altitude_source: Literal["gnss_msl", "configured_msl", "unknown"] = "gnss_msl"
    position_source: PositionSource = "gnss_live"

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
    position_delta_m: int = Field(default=0, ge=0)
    position_warn: bool = False
    position_suspect: bool = False
    time_suspect: bool = False
    time_holdover: bool = False
    position_trust: PositionTrustState = "UNCONFIGURED"
    time_trust: TimeTrustState = "UNKNOWN"


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


class SpatialInfo(BaseModel):
    """Compact 3+1 spatial payload.

    TDOA convention is tau_1j = t_j - t_1 in microseconds. The three
    independent reference delays are enough to solve a non-coplanar 3+1
    geometry. The remaining pair delays are derived exactly on the server.
    """

    tdoa12_us: int = 0
    tdoa13_us: int = 0
    tdoa14_us: int = 0
    residual_us: int = Field(default=0, ge=0)
    confidence_u8: int = Field(default=0, ge=0, le=255)
    geometry_id: int = Field(default=0, ge=0, le=255)
    tdoa_valid: bool = False
    direction_valid: bool = False

    @property
    def confidence(self) -> float:
        return self.confidence_u8 / 255.0

    @property
    def pair_tdoas_us(self) -> dict[str, int]:
        return {
            "tdoa12_us": self.tdoa12_us,
            "tdoa13_us": self.tdoa13_us,
            "tdoa14_us": self.tdoa14_us,
            "tdoa23_us": self.tdoa13_us - self.tdoa12_us,
            "tdoa24_us": self.tdoa14_us - self.tdoa12_us,
            "tdoa34_us": self.tdoa14_us - self.tdoa13_us,
        }


class PowerStatus(BaseModel):
    battery_pct: int = Field(default=0, ge=0, le=100)
    battery_mv: int = 0
    solar_mv: int = 0
    temperature_c10: int = 200
    battery_bus_mv: int | None = None
    battery_current_ma: int | None = None
    battery_power_mw: int | None = None
    monitor_status: int | None = Field(default=None, ge=0, le=255)

    @property
    def temperature_c(self) -> float:
        return self.temperature_c10 / 10.0

    @property
    def battery_bus_v(self) -> float | None:
        return None if self.battery_bus_mv is None else self.battery_bus_mv / 1000.0

    @property
    def battery_current_a(self) -> float | None:
        return None if self.battery_current_ma is None else self.battery_current_ma / 1000.0

    @property
    def battery_power_w(self) -> float | None:
        return None if self.battery_power_mw is None else self.battery_power_mw / 1000.0

    @property
    def monitor_valid(self) -> bool:
        return self.monitor_status == 0


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
    spatial: SpatialInfo = Field(default_factory=SpatialInfo)
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
    schema_ver: int = 1
    station_id: int
    seq_no: int
    boot_id: int = 0
    event_id: int
    event_time_us: int
    features: list[float]
    detector_profile: Literal["piston", "reactive", "generic"] = "generic"
    air_target_confirmed: bool = False

    @field_validator("features")
    @classmethod
    def validate_features(cls, value: list[float]) -> list[float]:
        if len(value) != FEATURE_COUNT:
            raise ValueError(f"features must contain exactly {FEATURE_COUNT} values")
        return [float(v) for v in value]


class OnlineTypeStatusMessage(BaseModel):
    station_id: int
    event_id: int
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    evidence_windows: int = Field(default=0, ge=0, le=8)
    required_windows: int = 4
    max_windows: int = 8
    family_label: str = "UNKNOWN"
    family_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    family_margin: float = 0.0
    family_status: str = "unknown"
    family_operational_validation_ready: bool = False
    family_conditional_on_air_target: bool = False
    family_model_version: str = "unknown"
    best_label: str = "UNKNOWN"
    hierarchical_label: str = "UNKNOWN"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    margin: float = 0.0
    status: str = "unknown"
    type_lock_allowed: bool = False
    first_type_hypothesis_seconds: float | None = None
    research_stable_seconds: float | None = None
    model_version: str = "unknown"


class CellularTelemetry(BaseModel):
    imsi: str = Field(pattern=r"^[0-9]{14,16}$")
    iccid: str = Field(pattern=r"^[0-9]{18,22}$")
    home_plmn: str = Field(default="", pattern=r"^(?:[0-9]{5,6})?$")
    registered_operator: str = Field(default="", max_length=31)
    apn: str = Field(min_length=1, max_length=63, pattern=r"^[A-Za-z0-9.-]+$")
    local_address: str = Field(min_length=1, max_length=63)
    gateway: str = Field(min_length=1, max_length=63)
    primary_dns: str = Field(min_length=1, max_length=63)
    secondary_dns: str = Field(default="", max_length=63)
    access_technology: int = Field(default=0, ge=0, le=255)
    apn_source: Literal["EXPLICIT", "NETWORK", "CATALOG"]
    settings_valid: Literal[True]


class HeartbeatMessage(BaseModel):
    station_id: int
    time_us: int
    station: StationPosition
    gnss: GnssStatus = Field(default_factory=GnssStatus)
    gnss_observed: StationPosition | None = None
    power: PowerStatus = Field(default_factory=PowerStatus)
    route: RouteStatus = Field(default_factory=RouteStatus)
    firmware_ver: str = "0.0.0"
    model_ver: str = "unknown"
    hardware_rev: str = "EVT"
    self_test_ok: bool = True
    fault_flags: list[str] = Field(default_factory=list)
    cellular: CellularTelemetry | None = None


class SecurityEventMessage(BaseModel):
    schema_ver: int = 1
    station_id: int
    seq_no: int
    boot_id: int = 0
    event_id: int
    event_time_us: int
    station: StationPosition
    reason: Literal[
        "case_open",
        "movement",
        "tilt",
        "power_loss",
        "gnss_spoof",
        "gnss_jam",
        "position_drift",
        "time_integrity",
        "other",
    ]
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
    localization_mode: Literal[
        "SINGLE_DOA",
        "TWO_STATION_COARSE",
        "HYBRID_3_2D5D",
        "FULL_3D",
        "CORRIDOR",
    ] = "SINGLE_DOA"
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
