// Dioneya EVT-PRE-20 geometry reference only.
// Not a production part. Units are millimetres.

triangle_side = 120;
upper_offset = 150;
marker_diameter = 10;
marker_height = 4;
strut_diameter = 4;

circumradius = triangle_side / sqrt(3);

mic1 = [0, circumradius, 0];
mic2 = [-triangle_side / 2, -circumradius / 2, 0];
mic3 = [triangle_side / 2, -circumradius / 2, 0];
mic4 = [0, 0, upper_offset];

module marker(position, label_text) {
    translate(position) {
        cylinder(d = marker_diameter, h = marker_height, center = true, $fn = 48);
        translate([0, 0, marker_height]) linear_extrude(0.6)
            text(label_text, size = 4, halign = "center", valign = "center");
    }
}

module strut(a, b, diameter = strut_diameter) {
    hull() {
        translate(a) sphere(d = diameter, $fn = 24);
        translate(b) sphere(d = diameter, $fn = 24);
    }
}

strut(mic1, mic2);
strut(mic2, mic3);
strut(mic3, mic1);
strut([0, 0, 0], mic4);

marker(mic1, "MIC1");
marker(mic2, "MIC2");
marker(mic3, "MIC3");
marker(mic4, "MIC4");

