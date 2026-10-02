"""Rev C preliminary acoustic head, preserving the ordered PCB-MIC Rev B.

All dimensions mm. Foam is an envelope, not a printed or qualified part.
The base closes the underside; a split sealed hatch passes terminated looms.
Four pairs of foam-retaining plates are integral with the upper ring.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "case_work/deps"))
import cadquery as cq  # noqa: E402

RELEASE = ROOT / "outputs/EVT_PRE_20_ПРОИЗВОДСТВЕННЫЙ_КОМПЛЕКТ_20261002_REV_D4"
PRINT = RELEASE / "Основной_пакет/03_Корпуса_для_3D_печати_ПРЕДВАРИТЕЛЬНО"
OUT = PRINT / "Акустическая_голова_3плюс1"
PODS = PRINT / "Микрофонный_модуль"
GEOMETRY = ROOT / "outputs/repo_pcbmain/mechanics/common/ACOUSTIC_GEOMETRY.csv"
HEAD = "DIO-3DP-AH-001C"
POD = "DIO-3DP-MC-001B"
BOARD_SHA = "c57cebbb3886247166551fd242fa51350bc9be7fee6299e63e7eaac60518d518"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cyl(x, y, z, radius, h):
    return cq.Workplane("XY").center(x, y).circle(radius).extrude(h).translate((0, 0, z))


def rect(x, y, z, dx, dy, dz):
    return cq.Workplane("XY").box(dx, dy, dz, centered=False).translate((x, y, z))


def beam(a, b, z, width, h):
    vx, vy = b[0]-a[0], b[1]-a[1]
    length = math.hypot(vx, vy)
    nx, ny = -vy/length*width/2, vx/length*width/2
    return (cq.Workplane("XY").polyline([(a[0]+nx,a[1]+ny), (b[0]+nx,b[1]+ny),
                                        (b[0]-nx,b[1]-ny), (a[0]-nx,a[1]-ny)])
            .close().extrude(h).translate((0,0,z)))


def rotated_box(r0, r1, z, height, angle, width=14):
    return rect(r0, -width/2, z, r1-r0, width, height).rotate((0,0,0),(0,0,1),angle)


def export(shape, name, print_part=True):
    target = OUT / f"{HEAD}_{name}"
    cq.exporters.export(shape, str(target.with_suffix(".step")), exportType="STEP")
    if print_part:
        ascii_path = ROOT / "outputs/evt_packet_work/_stl_ascii" / (target.name + ".stl")
        ascii_path.parent.mkdir(parents=True, exist_ok=True)
        cq.exporters.export(shape, str(ascii_path), exportType="STL", tolerance=0.08,
                            angularTolerance=0.10)
        assert ascii_path.stat().st_size > 84
        shutil.copy2(ascii_path, target.with_suffix(".stl"))


def make():
    with GEOMETRY.open(encoding="utf-8-sig", newline="") as stream:
        mic = {r["Mic_ID"]: tuple(float(r[k]) for k in ("X_mm","Y_mm","Z_mm"))
               for r in csv.DictReader(stream)}
    assert set(mic) == {"MIC1","MIC2","MIC3","MIC4"}
    assert mic["MIC4"] == (0,0,150)
    for a,b in (("MIC1","MIC2"),("MIC2","MIC3"),("MIC3","MIC1")):
        assert abs(math.dist(mic[a],mic[b])-120) < 0.001
    pod_report = json.loads((PODS/f"{POD}_fit_report.json").read_text(encoding="utf-8"))
    assert pod_report["source_board_sha256"] == BOARD_SHA
    OUT.mkdir(parents=True,exist_ok=True)
    for old in OUT.glob("DIO-3DP-AH-001B_*"):
        old.unlink()
    old_source=OUT/"CAD_GENERATOR_rev_b.py"
    if old_source.exists():old_source.unlink()

    # Closed Ø216 floor, 6 mm thick, with a raised inner collar around the
    # split cable hatch. The lower ring grows from this disk as one piece.
    floor=cyl(0,0,0,108,6)
    lower_ring=cyl(0,0,6,108,8).cut(cyl(0,0,5.9,93,8.2))
    collar=cyl(0,0,6,30,6).cut(cyl(0,0,5.9,26,6.2))
    base=floor.union(lower_ring).union(collar).cut(cyl(0,0,-0.1,26,12.2))
    for angle in (45,135,225,315):
        for r0,r1 in ((95.1,96.1),(106.5,107.5)):
            base=base.cut(rotated_box(r0-0.15,r1+0.15,10,4.1,angle,width=14.4))

    carrier=cyl(0,0,30,18,6)
    for name in ("MIC1","MIC2","MIC3"):
        x,y,_=mic[name]
        rad=math.hypot(x,y); anchor=(100*x/rad,100*y/rad)
        carrier=carrier.union(beam((0,0),anchor,30,10,6)).union(cyl(x,y,30,18,6))
        base=base.union(cyl(anchor[0],anchor[1],14,4.5,16))
        for dx in (-10,10):
            carrier=carrier.cut(cyl(x+dx,y-9,29.9,1.4,6.2))
    base=base.union(carrier).cut(cyl(0,0,29.9,8.1,6.2))
    # Floor pits collect drips inside the head, each with a 2.2 mm outward
    # side bore. The outer dome/foam condensate also reaches the floor.
    drain_angles=(10,100,190,280)
    for angle in drain_angles:
        theta=math.radians(angle)
        x,y=87*math.cos(theta),87*math.sin(theta)
        base=base.cut(cyl(x,y,2.5,4.5,3.6))
        bore=cq.Solid.makeCylinder(1.1,23,cq.Vector(x,y,3.6),
                                   cq.Vector(math.cos(theta),math.sin(theta),0))
        base=base.cut(bore)
    # Four blind pilots retain the two-piece cable hatch from beneath.
    for angle in (45,135,225,315):
        theta=math.radians(angle)
        base=base.cut(cyl(28*math.cos(theta),28*math.sin(theta),-0.1,1.05,4.1))
    mast=cyl(0,0,0,8,150).cut(cyl(0,0,-0.1,4,150.2))
    upper=cyl(0,0,0,18,6).cut(cyl(0,0,-0.1,8.1,6.2))
    for dx in (-10,10):
        upper=upper.cut(cyl(dx,-9,-0.1,1.4,6.2))

    # Eight slim plates, four radial pairs, are UNIONED with the upper ring
    # and middle visual belt. The complete cage is one printable solid.
    # Its bottom tongues enter blind sockets in the closed floor ring.
    cage=cyl(0,0,216,108,8).cut(cyl(0,0,215.9,93,8.2))
    middle_belt=cyl(0,0,112,108,6).cut(cyl(0,0,111.9,106.5,6.2))
    cage=cage.union(middle_belt)
    for angle in (45,135,225,315):
        for r0,r1 in ((95.1,96.1),(106.5,107.5)):
            cage=cage.union(rotated_box(r0,r1,10,210,angle,width=14))
    # Blind pilots in the upper ring accept dome fasteners; the foam slot
    # below remains free of protruding screw ends.
    for angle in (45,135,225,315):
        th=math.radians(angle)
        cage=cage.cut(cyl(101*math.cos(th),101*math.sin(th),219.9,1.35,4.2))

    # A split under-floor hatch lets already terminated four H-MIC looms
    # pass the base without threading their connectors through small bores.
    # The 0.4 mm perimeter and parting clearances require elastomer sealing.
    hatch=cyl(0,0,0,25.6,12).union(cyl(0,0,-3,31,3))
    for x in (-15,-5,5,15):
        hatch=hatch.cut(cyl(x,0,-3.1,2.2,15.2))
    for angle in (45,135,225,315):
        th=math.radians(angle)
        hatch=hatch.cut(cyl(28*math.cos(th),28*math.sin(th),-3.1,1.45,3.2))
    hatch_north=hatch.intersect(rect(-32,0.2,-3,64,32,15))
    hatch_south=hatch.intersect(rect(-32,-32.2,-3,64,32,15))

    # Lift only the crown by 10 mm, leaving MIC4, its carrier and every
    # harness route fixed. Acoustic benefit remains a physical test item.
    # A 3 mm shell and 4 mm mounting flange are separate.
    radius,rise=108.0,65.0
    sphere_radius=(radius**2+rise**2)/(2*rise)
    zc=rise-sphere_radius
    outside=cq.Workplane("XY").sphere(sphere_radius).translate((0,0,zc))
    inside=cq.Workplane("XY").sphere(sphere_radius-3).translate((0,0,zc))
    cap=outside.cut(inside).intersect(rect(-109,-109,0,218,218,66))
    flange=cyl(0,0,-4,108,4).cut(cyl(0,0,-4.1,93,4.2))
    for angle in (45,135,225,315):
        th=math.radians(angle)
        flange=flange.cut(cyl(101*math.cos(th),101*math.sin(th),-4.1,1.7,4.2))
    dome=cap.union(flange)
    foam=cyl(0,0,0,106.3,202).cut(cyl(0,0,-0.1,96.3,202.2))
    # Local notches keep the three lower ring-to-triangle posts out of the
    # flexible foam cutting envelope. Their final cutting pattern is tested
    # on the first physical assembly.
    for name in ("MIC1","MIC2","MIC3"):
        x,y,_=mic[name];rad=math.hypot(x,y)
        foam=foam.cut(cyl(100*x/rad,100*y/rad,-0.1,5.3,22.2))

    parts={"sealed_floor_carrier":base,"cable_hatch_north":hatch_north,
           "cable_hatch_south":hatch_south,"central_mast":mast,
           "upper_carrier":upper,"integral_upper_cage":cage,"dome":dome}
    sizes={}
    for name,shape in parts.items():
        assert shape.val().isValid(),name
        assert len(shape.val().Solids())==1,(name,"disconnected geometry")
        bb=shape.val().BoundingBox()
        sizes[name]=[round(bb.xlen,3),round(bb.ylen,3),round(bb.zlen,3)]
        assert max(bb.xlen,bb.ylen,bb.zlen) <= 216.01,(name,sizes[name])
        export(shape,name)
    export(foam,"foam_cut_envelope_NOT_PRINT",False)
    pod_body=cq.importers.importStep(str(PODS/f"{POD}_body.step"))
    pod_lid=cq.importers.importStep(str(PODS/f"{POD}_lid.step"))
    assy=cq.Assembly(name=f"{HEAD}_TRIAL_FIT")
    assy.add(base,name="SEALED_LOWER_FLOOR_AND_TRIANGLE",color=cq.Color(0.25,0.27,0.30))
    assy.add(hatch_north,name="SPLIT_CABLE_HATCH_NORTH_SEAL_REQUIRED",color=cq.Color(0.24,0.27,0.30))
    assy.add(hatch_south,name="SPLIT_CABLE_HATCH_SOUTH_SEAL_REQUIRED",color=cq.Color(0.24,0.27,0.30))
    assy.add(mast.translate((0,0,30)),name="CENTRAL_MAST",color=cq.Color(0.4,0.42,0.45))
    assy.add(upper.translate((0,0,180)),name="UPPER_CARRIER",color=cq.Color(0.3,0.32,0.35))
    assy.add(cage,name="ONE_PIECE_UPPER_RING_AND_EIGHT_PLATES",
             color=cq.Color(0.20,0.23,0.26))
    assy.add(foam.translate((0,0,14)),name="FOAM_ENVELOPE_ONLY",
             color=cq.Color(0.1,0.11,0.12,0.25))
    assy.add(dome.translate((0,0,228)),name="HIGHER_DOME",color=cq.Color(0.25,0.27,0.30))
    positions={}
    for name in ("MIC1","MIC2","MIC3","MIC4"):
        x,y,z=mic[name]; body_z=40+z
        assy.add(pod_body.translate((x,y,body_z)),name=f"{name}_BODY",color=cq.Color(0.38,0.40,0.42))
        assy.add(pod_lid.translate((x,y,body_z-4)),name=f"{name}_LID",color=cq.Color(0.36,0.38,0.40))
        positions[name]=[round(x,6),round(y,6),round(60+z,6)]
    assy.save(str(OUT/f"{HEAD}_full_fit_assembly.step"),exportType="STEP")
    report={
        "schema":"dioneya-acoustic-head-trial-v3", "status":"PRELIMINARY_PHYSICAL_VALIDATION_REQUIRED",
        "appearance_basis":"Рисунок11.png and Рисунок1.png", "source_board_sha256":BOARD_SHA,
        "coordinate_authority":"mechanics/common/ACOUSTIC_GEOMETRY.csv",
        "dome_rise_mm":65,"previous_dome_rise_mm":55,"head_outer_diameter_mm":216,
        "head_height_with_hatch_mm":296,"dome_inner_apex_z_mm":290,
        "clearance_above_mic4_acoustic_centre_mm":80,
        "foam_nominal_thickness_mm":10,"foam_max_requested_mm":15,
        "foam_radial_slot_mm":10.4,"foam_envelope_outer_diameter_mm":212.6,
        "foam_envelope_height_mm":202,"foam_lower_post_notch_count":3,
        "plate_pair_count":4,"upper_ring_and_eight_plates_integral":True,
        "lower_floor_thickness_mm":6,"lower_floor_open_center_hatch_diameter_mm":52,
        "split_hatch_seal":"MANDATORY_ELASTOMER_PERIMETER_SEAM_AND_FOUR_CABLE_GROOVES",
        "cable_groove_diameter_mm":4.4,"cable_bundle_od":"MEASURE_ON_FIRST_HARNESS",
        "condensate_pocket_count":4,"condensate_pocket_angles_deg":drain_angles,
        "pocket_diameter_mm":9,"pocket_depth_mm":3.5,
        "outward_drain_diameter_mm":2.2,"acoustic_centres_world_mm":positions,
        "print_parts_per_station":{"sealed_floor_carrier":1,"cable_hatch_north":1,
          "cable_hatch_south":1,"central_mast":1,"upper_carrier":1,
          "integral_upper_cage":1,"dome":1,
          "mic_pod_body":4,"mic_pod_lid":4},
        "source_for_foam_trial":"https://acoustics.asn.au/conference_proceedings/INTERNOISE2014/papers/p844.pdf",
        "source_scope":"10 mm open-cell foam is a design analogue, not verified attenuation for this device",
        "part_bounding_boxes_mm":sizes,
        "physical_checks_open":["foam MPN, porosity and acoustic transfer function",
          "wind attenuation, dome-height acoustic effect and underside leakage of 3+1 head", "wet foam and rain/drain test",
          "fit with actual PCBA, J1 and preterminated H-MIC looms",
          "measure loom outside diameter and qualify hatch elastomer seal",
          "minimum 230 mm print bed with brim; orientation, warping and shrinkage",
          "one-piece cage strength, dome inserts and torque", "mast mount and cable routes"],
        "files":{p.name:sha(p) for p in sorted(OUT.glob(f"{HEAD}*"))
                 if p.is_file() and p.suffix.lower() in (".step",".stl")},
    }
    (OUT/f"{HEAD}_fit_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"head":HEAD,"size_mm":sizes,"acoustic_centres":positions},ensure_ascii=False))


if __name__=="__main__":
    make()
