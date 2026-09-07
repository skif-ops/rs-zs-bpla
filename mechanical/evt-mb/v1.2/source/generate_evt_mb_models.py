#!/usr/bin/env python3
"""Generate printable EVT-MB reference geometry without external CAD packages."""
from __future__ import annotations

import csv
import json
import math
import struct
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
PREVIEW_DIR = ROOT / "previews"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def box(x, y, z, dx, dy, dz):
    v = [(x,y,z),(x+dx,y,z),(x+dx,y+dy,z),(x,y+dy,z),
         (x,y,z+dz),(x+dx,y,z+dz),(x+dx,y+dy,z+dz),(x,y+dy,z+dz)]
    f = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
         (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(v[a],v[b],v[c]) for a,b,c in f]


def cylinder(cx, cy, z, radius, height, segments=48):
    tris = []
    cb, ct = (cx,cy,z), (cx,cy,z+height)
    for i in range(segments):
        a = 2*math.pi*i/segments; b = 2*math.pi*(i+1)/segments
        p0=(cx+radius*math.cos(a),cy+radius*math.sin(a),z)
        p1=(cx+radius*math.cos(b),cy+radius*math.sin(b),z)
        q0=(p0[0],p0[1],z+height); q1=(p1[0],p1[1],z+height)
        tris += [(cb,p1,p0),(ct,q0,q1),(p0,p1,q1),(p0,q1,q0)]
    return tris


def ring(cx, cy, z, r_outer, r_inner, height, segments=48):
    tris=[]
    for i in range(segments):
        a=2*math.pi*i/segments; b=2*math.pi*(i+1)/segments
        ob=(cx+r_outer*math.cos(a),cy+r_outer*math.sin(a),z)
        on=(cx+r_outer*math.cos(b),cy+r_outer*math.sin(b),z)
        ot=(ob[0],ob[1],z+height); otn=(on[0],on[1],z+height)
        ib=(cx+r_inner*math.cos(a),cy+r_inner*math.sin(a),z)
        inn=(cx+r_inner*math.cos(b),cy+r_inner*math.sin(b),z)
        it=(ib[0],ib[1],z+height); itn=(inn[0],inn[1],z+height)
        tris += [(ob,on,otn),(ob,otn,ot),(inn,ib,it),(inn,it,itn),
                 (ot,otn,itn),(ot,itn,it),(ob,ib,inn),(ob,inn,on)]
    return tris


def rotate_z(mesh, angle_deg, origin=(0.0,0.0)):
    a=math.radians(angle_deg); c,s=math.cos(a),math.sin(a); ox,oy=origin
    def rot(p):
        x,y,z=p; x-=ox; y-=oy
        return (ox+x*c-y*s,oy+x*s+y*c,z)
    return [(rot(a),rot(b),rot(c_)) for a,b,c_ in mesh]


def translate(mesh, dx=0, dy=0, dz=0):
    def tr(p): return (p[0]+dx,p[1]+dy,p[2]+dz)
    return [(tr(a),tr(b),tr(c)) for a,b,c in mesh]


def tray(width, depth, height, wall=3.0, floor=3.0):
    # Small overlaps avoid coplanar/touching seams between closed primitives.
    # FlashPrint unions the overlapping watertight shells during slicing.
    overlap = 0.2
    return (box(0,0,0,width,depth,floor)+
            box(0,0,floor-overlap,wall,depth,height-floor+overlap)+
            box(width-wall,0,floor-overlap,wall,depth,height-floor+overlap)+
            box(wall-overlap,0,floor-overlap,width-2*wall+2*overlap,wall,height-floor+overlap)+
            box(wall-overlap,depth-wall,floor-overlap,width-2*wall+2*overlap,wall,height-floor+overlap))


def lid(width, depth, panel=3.0, lip=2.0, wall=2.4):
    overlap=0.2
    mesh=box(0,0,lip-overlap,width,depth,panel+overlap)
    mesh+=box(wall,wall,0,width-2*wall,wall,lip)
    mesh+=box(wall,depth-2*wall,0,width-2*wall,wall,lip)
    mesh+=box(wall,2*wall-overlap,0,wall,depth-4*wall+2*overlap,lip)
    mesh+=box(width-2*wall,2*wall-overlap,0,wall,depth-4*wall+2*overlap,lip)
    return mesh


def electronics_base():
    mesh=tray(180,140,66,3.2,3.2)
    for x in (14,166):
        for y in (14,126): mesh += ring(x,y,3.2,5.0,1.7,8.0,32)
    mesh += box(25,25,3.2,130,3,6)+box(25,112,3.2,130,3,6)
    return mesh


def battery_base():
    mesh=tray(180,125,108,4.0,4.0)
    mesh += box(12,10,4,3,105,8)+box(165,10,4,3,105,8)
    for x in (12,168):
        for y in (12,113): mesh += ring(x,y,4,5.5,1.8,8,32)
    return mesh


def mic_pod():
    # Adjustable EVT tray for 12–19 mm I2S breakout boards; verify fit before batch print.
    mesh=tray(28.0,24.0,8.0,2.5,2.0)
    mesh += box(2.5,10.5,1.8,3.0,3.0,6.2)  # cable strain relief island; 0.2 mm overlap
    return mesh


def mic_base():
    mesh=cylinder(0,0,0,18,4,64)+ring(0,0,4,11,7,8,48)
    radius=120/math.sqrt(3)
    for angle in (90,210,330):
        arm=box(-7,8,0,14,radius-8,5)
        mesh += rotate_z(arm,angle-90)
        x=radius*math.cos(math.radians(angle)); y=radius*math.sin(math.radians(angle))
        mesh += translate(mic_pod(),x-14.0,y-12.0,5)
    return mesh


def upper_mast():
    mesh=box(-14,-14,0,28,28,5)+ring(0,0,5,10.5,7.0,150,48)
    mesh += translate(mic_pod(),-14.0,-12.0,155)
    return mesh


def pole_mount_half():
    # Clamp half for 40-60 mm poles, with replaceable TPU/rubber shim.
    mesh=box(0,0,0,80,18,12)
    mesh+=ring(40,18,0,34,30,12,64)
    mesh+=box(4,-12,0,12,12,12)+box(64,-12,0,12,12,12)
    return mesh


MODELS={
    "evt_electronics_base": electronics_base(),
    "evt_electronics_lid": lid(180,140),
    "evt_battery_base": battery_base(),
    "evt_battery_lid": lid(180,125),
    "mic_pod_i2s_adjustable": mic_pod(),
    "mic_array_base_120": mic_base(),
    "mic_upper_mast_150": upper_mast(),
    "pole_mount_half_40_60": pole_mount_half(),
}


def normal(tri):
    a,b,c=tri
    ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3))
    nx,ny,nz=uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx
    length=math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
    return nx/length,ny/length,nz/length


def write_stl(path, mesh, name):
    with path.open("w",encoding="ascii") as f:
        f.write(f"solid {name}\n")
        for tri in mesh:
            n=normal(tri); f.write(f" facet normal {n[0]:.7g} {n[1]:.7g} {n[2]:.7g}\n  outer loop\n")
            for p in tri: f.write(f"   vertex {p[0]:.7g} {p[1]:.7g} {p[2]:.7g}\n")
            f.write("  endloop\n endfacet\n")
        f.write(f"endsolid {name}\n")


def write_3mf(path, mesh):
    verts=[]; ids={}; tris=[]
    for tri in mesh:
        row=[]
        for p in tri:
            key=tuple(round(v,6) for v in p)
            if key not in ids: ids[key]=len(verts); verts.append(key)
            row.append(ids[key])
        tris.append(row)
    vxml="".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x,y,z in verts)
    txml="".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a,b,c in tris)
    model=('<?xml version="1.0" encoding="UTF-8"?>'
           '<model unit="millimeter" xml:lang="ru-RU" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
           f'<resources><object id="1" type="model"><mesh><vertices>{vxml}</vertices><triangles>{txml}</triangles></mesh></object></resources>'
           '<build><item objectid="1"/></build></model>')
    types=('<?xml version="1.0" encoding="UTF-8"?>'
           '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
           '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
           '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels=('<?xml version="1.0" encoding="UTF-8"?>'
          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",types); z.writestr("_rels/.rels",rels); z.writestr("3D/3dmodel.model",model)


def bounds(mesh):
    pts=[p for tri in mesh for p in tri]
    mins=[min(p[i] for p in pts) for i in range(3)]; maxs=[max(p[i] for p in pts) for i in range(3)]
    return mins,maxs,[maxs[i]-mins[i] for i in range(3)]


def preview(path, mesh, title):
    fig=plt.figure(figsize=(6.4,5.0),dpi=150); ax=fig.add_subplot(111,projection="3d")
    coll=Poly3DCollection(mesh,facecolor="#69a7d0",edgecolor="#23536f",linewidth=0.15,alpha=0.92)
    ax.add_collection3d(coll); mn,mx,size=bounds(mesh)
    cx=[(mn[i]+mx[i])/2 for i in range(3)]; span=max(size)*0.58 or 1
    ax.set_xlim(cx[0]-span,cx[0]+span); ax.set_ylim(cx[1]-span,cx[1]+span); ax.set_zlim(max(0,cx[2]-span),cx[2]+span)
    ax.set_xlabel("X, мм"); ax.set_ylabel("Y, мм"); ax.set_zlabel("Z, мм"); ax.set_title(title)
    ax.view_init(elev=28,azim=-52); fig.tight_layout(); fig.savefig(path,bbox_inches="tight"); plt.close(fig)


manifest=[]
for name,mesh in MODELS.items():
    stl=MODEL_DIR/f"{name}.stl"; mf=MODEL_DIR/f"{name}.3mf"; png=PREVIEW_DIR/f"{name}.png"
    write_stl(stl,mesh,name); write_3mf(mf,mesh); preview(png,mesh,name)
    mn,mx,size=bounds(mesh)
    manifest.append({"name":name,"triangles":len(mesh),"bounds_mm":size,"fits_ad5m_pro":all(v<=220.0 for v in size),"stl":stl.name,"3mf":mf.name})

with (ROOT/"model_manifest.json").open("w",encoding="utf-8") as f:
    json.dump({"printer":"FlashForge Adventurer 5M Pro","build_volume_mm":[220,220,220],"models":manifest},f,ensure_ascii=False,indent=2)

with (ROOT/"print_job_matrix.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["Model","Qty per station","Material","Orientation","Supports","Notes"])
    rows={
      "evt_electronics_base":(1,"ASA","floor on bed","No","4 walls, 30% gyroid"),
      "evt_electronics_lid":(1,"ASA","outer face on bed","No","Use 3 mm gasket cord"),
      "evt_battery_base":(1,"ASA","floor on bed","No","4 walls, 30% gyroid"),
      "evt_battery_lid":(1,"ASA","outer face on bed","No","Use 3 mm gasket cord"),
      "mic_pod_i2s_adjustable":(4,"ASA","floor on bed","No","Print 5 per station including one spare; port upward"),
      "mic_array_base_120":(1,"ASA","flat","No","Triangle side 120 mm"),
      "mic_upper_mast_150":(1,"ASA","mast vertical","Yes, build plate only","Upper mic +150 mm"),
      "pole_mount_half_40_60":(2,"ASA","flat face on bed","No","Use rubber shim and M6 hardware"),
    }
    for n,(q,m,o,s,note) in rows.items(): w.writerow([n,q,m,o,s,note])

print(json.dumps(manifest,ensure_ascii=False,indent=2))
