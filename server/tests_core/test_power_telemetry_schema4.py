from station.cbor_codec import decode_detection_obj
import pytest


def _base(status: dict[int, int]) -> dict:
    return {
        0: 4,
        1: 2,
        2: 1001,
        3: 7,
        4: 3,
        5: 99,
        6: 1_780_000_000_000_000,
        7: 0,
        8: {},
        10: status,
        12: {},
        13: {},
        14: {},
    }


def test_schema4_full_decodes_ina226_fields():
    msg = decode_detection_obj(
        _base(
            {
                0: 81,
                1: 12_750,
                2: 18_100,
                3: 245,
                4: 0,
                5: 0,
                6: -72,
                7: 90,
                8: 11,
                9: 12_750,
                10: -500,
                11: 6_375,
                12: 0,
            }
        )
    )

    assert msg.schema_ver == 4
    assert msg.power.battery_mv == 12_750
    assert msg.power.battery_bus_mv == 12_750
    assert msg.power.battery_bus_v == 12.75
    assert msg.power.battery_current_ma == -500
    assert msg.power.battery_current_a == -0.5
    assert msg.power.battery_power_mw == 6_375
    assert msg.power.battery_power_w == 6.375
    assert msg.power.monitor_status == 0
    assert msg.power.monitor_valid


def test_summary_remains_backward_compatible_without_ina226_extension():
    obj = _base({0: 81, 1: 12_750, 2: 18_100, 3: 245, 4: 3, 5: 2, 6: -95, 7: 40, 8: 17})
    obj[0] = 3
    msg = decode_detection_obj(obj)

    assert msg.power.battery_mv == 12_750
    assert msg.power.battery_bus_mv is None
    assert msg.power.battery_current_ma is None
    assert msg.power.battery_power_mw is None
    assert msg.power.monitor_status is None
    assert not msg.power.monitor_valid


@pytest.mark.parametrize("schema_ver", [0, 2, 5, 255])
def test_unsupported_detection_schema_is_rejected(schema_ver: int):
    obj = _base({})
    obj[0] = schema_ver
    with pytest.raises(ValueError, match="unsupported compact detection schema"):
        decode_detection_obj(obj)
