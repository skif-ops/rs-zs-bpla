"""Constant-velocity 3D Kalman filter for target tracking."""
from __future__ import annotations
import numpy as np

class ConstantVelocityKalman3D:
    def __init__(self, process_accel_sigma: float = 12.0):
        self.x: np.ndarray | None = None
        self.p: np.ndarray | None = None
        self.t: float | None = None
        self.q_accel = float(process_accel_sigma) ** 2
    def _predict_matrices(self, dt: float):
        f=np.eye(6); f[0,3]=dt; f[1,4]=dt; f[2,5]=dt
        g=np.array([[0.5*dt*dt,0,0],[0,0.5*dt*dt,0],[0,0,0.5*dt*dt],[dt,0,0],[0,dt,0],[0,0,dt]],float)
        q=g @ (np.eye(3)*self.q_accel) @ g.T
        return f,q
    def update(self, pos_enu: np.ndarray, t_seconds: float, sigma_m: float = 80.0) -> np.ndarray:
        z=np.asarray(pos_enu,dtype=float).reshape(3)
        if self.x is None:
            self.x=np.r_[z,[0.,0.,0.]]; self.p=np.diag([sigma_m**2]*3+[200.0**2]*3); self.t=t_seconds
            return self.x.copy()
        dt=max(float(t_seconds-self.t),0.001); self.t=t_seconds
        f,q=self._predict_matrices(dt); self.x=f@self.x; self.p=f@self.p@f.T+q
        h=np.zeros((3,6)); h[:3,:3]=np.eye(3); r=np.eye(3)*max(sigma_m,5.0)**2
        y=z-h@self.x; s=h@self.p@h.T+r; k=self.p@h.T@np.linalg.inv(s)
        self.x=self.x+k@y; self.p=(np.eye(6)-k@h)@self.p
        return self.x.copy()
    def predict(self, t_seconds: float) -> np.ndarray | None:
        if self.x is None or self.t is None: return None
        dt=max(t_seconds-self.t,0.0); f,_=self._predict_matrices(dt); return f@self.x
