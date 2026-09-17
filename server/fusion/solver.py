"""Station-network localization using DOA and arrival-time TDOA."""
from __future__ import annotations
import math
import numpy as np
from scipy.optimize import least_squares
from station.schemas import DetectionMessage, TargetEstimate
from fusion.geodesy import EnuFrame

def speed_of_sound(temp_c: float) -> float:
    return 331.3 + 0.606 * float(temp_c)

def _frame(dets: list[DetectionMessage]) -> EnuFrame:
    lat=sum(d.station.lat for d in dets)/len(dets); lon=sum(d.station.lon for d in dets)/len(dets); alt=sum(d.station.alt_m for d in dets)/len(dets)
    return EnuFrame(lat,lon,alt)

def _stations_enu(dets, frame):
    return np.asarray([frame.to_enu(d.station.lat,d.station.lon,d.station.alt_m) for d in dets])

def _geometry_mode(dets: list[DetectionMessage], frame: EnuFrame) -> tuple[str, str]:
    count=len(dets)
    if count < 2: return 'SINGLE_DOA','invalid'
    if count == 2: return 'TWO_STATION_COARSE','poor'
    xy=_stations_enu(dets,frame)[:,:2]
    centered=xy-np.mean(xy,axis=0)
    singular=np.linalg.svd(centered,compute_uv=False)
    ratio=float(singular[-1]/max(singular[0],1e-9)) if len(singular)>1 else 0.0
    if ratio < 0.08: return 'CORRIDOR','poor'
    if count == 3: return 'HYBRID_3_2D5D','acceptable'
    return 'FULL_3D','good' if ratio >= 0.25 else 'acceptable'

def _tdoa_allowed(d: DetectionMessage) -> bool:
    # The approved detection wire schema 4 carries PPS state and expected time error in
    # payload key 8.  Newer in-memory messages may also expose time_status.
    # Keep both representations compatible during the EVT transition.
    time_status = getattr(d, 'time_status', None)
    if time_status is not None and time_status.quality != 'INVALID':
        return time_status.tdoa_allowed and time_status.uncertainty_us <= 1000
    return d.gnss.pps_ok and d.gnss.expected_time_error_us <= 1000

def _doa_point(dets: list[DetectionMessage], frame: EnuFrame):
    valid=[d for d in dets if d.doa.valid]
    if len(valid)<2: return None, None
    a=[]; b=[]; zvals=[]
    for d in valid:
        p=frame.to_enu(d.station.lat,d.station.lon,d.station.alt_m)
        az=math.radians(d.doa.azimuth_deg)
        # direction in ENU: east=sin(az), north=cos(az)
        v=np.array([math.sin(az),math.cos(az)])
        n=np.array([-v[1],v[0]])
        w=1.0/max(d.doa.sigma_deg,1.0)
        a.append(n*w); b.append(float(n@p[:2])*w)
    A=np.asarray(a); B=np.asarray(b)
    if np.linalg.matrix_rank(A)<2: return None,None
    xy,*_=np.linalg.lstsq(A,B,rcond=None)
    for d in valid:
        p=frame.to_enu(d.station.lat,d.station.lon,d.station.alt_m)
        rho=float(np.linalg.norm(xy-p[:2]))
        elev=math.radians(d.doa.elevation_deg)
        if abs(d.doa.elevation_deg)<80: zvals.append(p[2]+rho*math.tan(elev))
    z=float(np.median(zvals)) if zvals else 300.0
    residuals=np.abs(A@xy-B); sigma=max(float(np.median(residuals))*2.0,50.0)
    return np.array([xy[0],xy[1],z]), sigma

def _tdoa_point(dets: list[DetectionMessage], frame: EnuFrame, initial: np.ndarray | None):
    valid=[d for d in dets if _tdoa_allowed(d)]
    if len(valid)<4: return None,None
    pos=_stations_enu(valid,frame)
    t=np.array([d.event_time_us for d in valid],dtype=float)*1e-6; t0=t.min(); dt=t-t0
    temps=[d.power.temperature_c for d in valid]; c=speed_of_sound(float(np.median(temps)))
    if initial is None:
        x0=np.r_[np.mean(pos[:,:2],axis=0), max(300.0, np.max(pos[:,2])+300.0), -1000.0]
    else:
        # b is range-equivalent source emission time relative to first arrival
        x0=np.r_[initial, -max(float(np.mean(np.linalg.norm(pos-initial,axis=1))),100.0)]
    def residual(v):
        xyz=v[:3]; b=v[3]
        return np.linalg.norm(pos-xyz,axis=1)+b-c*dt
    span=max(np.ptp(pos[:,0]),np.ptp(pos[:,1]),1000.0)
    lower=[np.min(pos[:,0])-10000,np.min(pos[:,1])-10000,-1000,-30000]
    upper=[np.max(pos[:,0])+10000,np.max(pos[:,1])+10000,8000,1000]
    res=least_squares(residual,x0,bounds=(lower,upper),loss='soft_l1',f_scale=50.0,max_nfev=600)
    rmse=float(np.sqrt(np.mean(res.fun**2)))
    if not res.success or not np.isfinite(rmse): return None,None
    return res.x[:3], max(rmse*3.0,25.0)

def solve_target(dets: list[DetectionMessage]) -> TargetEstimate:
    if len(dets)<2: return TargetEstimate()
    frame=_frame(dets)
    mode,geometry_quality=_geometry_mode(dets,frame)
    doa,sigma_doa=_doa_point(dets,frame)
    tdoa,sigma_tdoa=_tdoa_point(dets,frame,doa)
    if tdoa is not None:
        xyz=tdoa; sigma=sigma_tdoa; method='tdoa_3d'; quality='high' if sigma<=80 else 'medium' if sigma<=200 else 'low'
    elif doa is not None:
        xyz=doa; sigma=sigma_doa; method='doa_intersection'; quality='medium' if sigma<=150 else 'low'
    else:
        return TargetEstimate(localization_method='insufficient_geometry',localization_mode=mode,geometry_quality=geometry_quality,quality='invalid')
    lat,lon,alt=frame.to_geodetic(*xyz)
    if mode == 'CORRIDOR': quality='low'
    return TargetEstimate(lat=lat,lon=lon,alt_msl_m=alt,horizontal_error_m=sigma,vertical_error_m=max(sigma*1.5,50.0),localization_method=method,localization_mode=mode,geometry_quality=geometry_quality,quality=quality)
