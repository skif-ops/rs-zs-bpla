from fusion.solver import solve_target
from station.schemas import DetectionMessage

def det(station_id, lat, lon, azimuth_deg):
    return DetectionMessage(
        schema_ver=3, station_id=station_id, seq_no=1, event_id=station_id,
        event_time_us=2_000_000_000_000_000,
        station={'lat_e7':int(lat*1e7),'lon_e7':int(lon*1e7),'alt_dm':1000},
        gnss={'fix_type':3,'satellites':12,'hdop_x100':80,'pps_ok':True,'expected_time_error_us':80},
        classification={'class_id':1,'label':'PISTON_UAV','confidence_u8':230,'unknown':False},
        doa={'azimuth_cdeg':int(azimuth_deg*100),'elevation_cdeg':500,'sigma_cdeg':500,'valid':True},
    )

def test_three_non_collinear_is_hybrid():
    result=solve_target([det(1,55.0,37.0,45),det(2,55.0,37.02,315),det(3,55.01,37.01,180)])
    assert result.localization_mode == 'HYBRID_3_2D5D'

def test_four_collinear_is_corridor_not_full_3d():
    result=solve_target([det(i,55.0,37.0+i*0.01,180) for i in range(1,5)])
    assert result.localization_mode == 'CORRIDOR'

def test_degraded_time_is_not_tdoa_reference():
    items=[det(i,55.0+(i%2)*0.01,37.0+(i//2)*0.01,90) for i in range(1,5)]
    for item in items:
        item.gnss.pps_ok=False
        item.gnss.expected_time_error_us=100_000
    result=solve_target(items)
    assert result.localization_method != 'tdoa_3d'
