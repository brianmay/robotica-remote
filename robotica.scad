// GLOBALS
wall_thickness = 1;
radius = 10;

interior_height = 30;
height = interior_height + wall_thickness;

x_interior_depth=70;
y_interior_depth=70;

x_depth = x_interior_depth+wall_thickness*2;
y_depth = y_interior_depth+wall_thickness*2;

esp32_thickness = 5;

screw_head_diameter = 4.4;
screw_tube_diameter = 2.6;
screw_tube_outer_diameter = 5;
screw_insert_diameter = 3;

// cube([x_depth,y_depth,wall_thickness]);

// cube([wall_thickness, y_depth, height]);

// translate([x_depth-wall_thickness,0,0])
// cube([wall_thickness, y_depth, height]);

// cube([x_depth,wall_thickness,height]);

// translate([0,y_depth-wall_thickness,0]);
//cube([x_depth,wall_thickness,height]);

module wall(x_depth, y_depth, z_depth) {
    hull()
    for(x=[radius,x_depth-radius]) // repeat the following with two variants for x
    {
        for(y=[radius,y_depth-radius]) // repeat again but this time for y
        {
            translate([x,y,0])
            cylinder(r=radius,h=z_depth);
        }
    }
}

// BOTTOM + WALLS
*union() {
    // BOX 
    translate([-x_depth/2, -y_depth/2, -wall_thickness])
    difference()
    { 
        wall(x_depth, y_depth, height);
        translate([wall_thickness, wall_thickness, wall_thickness])
        wall(x_depth-wall_thickness*2, y_depth-wall_thickness*2, height);
        translate([-1,y_depth/2-6,esp32_thickness+wall_thickness-1])
        cube([wall_thickness+2,12,9]);
    }

    // BOX screw mounts
    for (x=[-x_interior_depth/2+4,x_interior_depth/2-4]) {
        for (y=[-y_interior_depth/2+4,y_interior_depth/2-4]) {
            translate([x,y,0])
            difference() {
                cylinder(r=screw_tube_outer_diameter/2,h=height-wall_thickness);
                cylinder(r=screw_insert_diameter/2,h=height);
            }
        }
    }

    // FLOOR
    translate([-9,0,0])
    {
        // battery
        bat_x_depth=35;
        bat_y_depth=62;
        bat_height=5;
        bat_support_width=1;
        bat_support_height=bat_height;
        
        // fake battery
        {
            translate([-bat_x_depth/2,-bat_y_depth/2,0])
            *cube([bat_x_depth,62,5]);
        }
        
        // battery supports
        {
            translate([bat_x_depth/2,-bat_y_depth/2,0])
            cube([bat_support_width,bat_y_depth,bat_support_height]);
            translate([-bat_x_depth/2-bat_support_width,-bat_y_depth/2,0])
            cube([bat_support_width,bat_y_depth,bat_support_height]);
            translate([-bat_x_depth/2-bat_support_width,bat_y_depth/2,0])
            cube([bat_x_depth+bat_support_width*2,bat_support_width,bat_support_height]);
            translate([-bat_x_depth/2-bat_support_width,-bat_y_depth/2-bat_support_width,0])
            cube([bat_x_depth+bat_support_width*2,bat_support_width,bat_support_height]);
        }
        
        // fake ESP32
        {
            esp32_x_depth=2*25.4;
            esp32_y_depth=0.9*25.4;
            translate([-esp32_x_depth/2,-esp32_y_depth/2,esp32_thickness])
            * cube([esp32_x_depth, esp32_y_depth, 2]);
        }
        
        // ESP32 supports
        esp32_s_x_depth=1.8*25.4;

        union() {
            esp32_s_y_depth_1=18;
            translate([-esp32_s_x_depth/2,-esp32_s_y_depth_1/2,0])
            difference() {
                cylinder(r=screw_tube_outer_diameter/2,h=esp32_thickness);
                cylinder(r=screw_insert_diameter/2,h=esp32_thickness+1);
            }
            translate([-esp32_s_x_depth/2,esp32_s_y_depth_1/2,0])
            difference() {
                cylinder(r=screw_tube_outer_diameter/2,h=esp32_thickness);
                cylinder(r=screw_insert_diameter/2,h=esp32_thickness+1);
            }

            esp32_s_y_depth_2=19.5;
            translate([esp32_s_x_depth/2,-esp32_s_y_depth_2/2,0]) {
                cylinder(r=screw_tube_outer_diameter/2,h=esp32_thickness);
                cylinder(r=2.3/2,h=esp32_thickness+1.5);
            }
            translate([esp32_s_x_depth/2,esp32_s_y_depth_2/2,0]) {
                cylinder(r=screw_tube_outer_diameter/2,h=esp32_thickness);
                cylinder(r=2.3/2,h=esp32_thickness+1.5);
            }

            *translate([-30,-15,0])
            cube([60,30,1]);
        }
    }      
}

// ROOF
led_height=3.2;
led_base=2;

led_outer_diameter=45.1;
led_inner_diameter=31;

groove_height=1;
groove_width=2;

roof_height=led_base+led_height;

screw_base=2;

!translate([0, 0, interior_height])
{
    difference() {
        // BOX
        translate([-x_depth/2, -y_depth/2, 0])
        wall(x_depth, y_depth, roof_height);

        // BOX screw mounts
        for (x=[-x_interior_depth/2+4,x_interior_depth/2-4]) {
            for (y=[-y_interior_depth/2+4,y_interior_depth/2-4]) {
                translate([x,y,-1])
                cylinder(r=screw_tube_diameter/2,h=roof_height+2);

                translate([x,y,screw_base])
                cylinder(r=screw_head_diameter/2,h=roof_height+2);
            }
        }

        // LED hole
        translate([0,0,led_base])
        cylinder(r=led_outer_diameter/2,h=led_height+1);

        // Groove for cables
        translate([0,0,led_base-groove_height])
        difference() {
            cylinder(r=led_outer_diameter/2,h=groove_height+1);
            translate([0,0,-1])
            cylinder(r=(led_outer_diameter)/2 - groove_width,h=groove_height+2);
        }

        // Access holes for cables
        translate([-(led_outer_diameter/2-groove_width/2 - 0.1), 0, -1])
        cylinder(r=groove_width/2, h=roof_height+2);

        translate([led_outer_diameter/2-groove_width/2 - 0.1, 0, -1])
        cylinder(r=groove_width/2, h=roof_height+2);

        translate([0, -(led_outer_diameter/2-groove_width/2 - 0.1), -1])
        cylinder(r=groove_width/2, h=roof_height+2);

        translate([0, led_outer_diameter/2-groove_width/2 - 0.1, -1])
        cylinder(r=groove_width/2, h=roof_height+2);

        // Access hole for buttons
        translate([0,0,-1])
        cylinder(r=led_inner_diameter/2,h=led_height+2);

        // Switch screw mounts
        for (x=[-led_outer_diameter/2,led_outer_diameter/2]) {
            for (y=[-led_outer_diameter/2,led_outer_diameter/2]) {
                translate([x,y,-1])
                cylinder(r=screw_insert_diameter/2,h=3+1);
            }
        }

    }

    // cross supports for buttons
    translate([-led_inner_diameter/2, -2/2, 0])
    cube([led_inner_diameter, 2, roof_height]);

    translate([-2/2, -led_inner_diameter/2, 0])
    cube([2, led_inner_diameter, roof_height]);
}

// SWITCHES
switch_width=12;
switch_depth=12;
switch_thickness=6;

switch_border_width=1;
switch_border_thickness=5.4;

lower_button_thickness = 1;
lower_button_width = switch_width + switch_border_width*2+2;
lower_button_depth = switch_depth + switch_border_width*2+2;

upper_button_thickness = roof_height + 1;

button_tolarance = 0.3;

switch_tray_width=led_outer_diameter + 10;
switch_tray_thickness=1;
switch_tray_height=switch_thickness + lower_button_thickness + 0.3;
switch_spacing=2;

module switch() {
    translate([switch_border_width, switch_border_width, 0]) {
        translate([1,0,-1])
        cube([switch_width,1,switch_tray_thickness+2]);
        
        translate([1,switch_depth+1,-1])
        cube([switch_width,1,switch_tray_thickness+2]);
    }
}

module switch_upper() {
    translate([switch_border_width, switch_border_width, 0]) {
        translate([-switch_border_width,-switch_border_width,switch_tray_thickness])
        cube([switch_border_width+1, switch_depth+2+2*switch_border_width, switch_border_thickness]);

        translate([switch_width+1,-switch_border_width,switch_tray_thickness])
        cube([switch_border_width+1, switch_depth+2+2*switch_border_width, switch_border_thickness]);

        translate([-switch_border_width,-switch_border_width,switch_tray_thickness])
        cube([switch_depth+2*switch_border_width, switch_border_width, switch_border_thickness]);

        translate([-switch_border_width,switch_depth+2, switch_tray_thickness])
        cube([switch_depth+2*switch_border_width, switch_border_width, switch_border_thickness]);
    }
}

translate([0, 0, interior_height-switch_tray_height-switch_tray_thickness - 0.1])
{
    difference() {
        translate([-switch_tray_width/2, -switch_tray_width/2, 0])
        cube([switch_tray_width, switch_tray_width, switch_tray_thickness]);

        // BOX screw mounts
        for (x=[-led_outer_diameter/2,led_outer_diameter/2]) {
            for (y=[-led_outer_diameter/2,led_outer_diameter/2]) {
                translate([x,y,-1])
                cylinder(r=screw_tube_diameter/2,h=switch_tray_thickness+2);
            }
        }

        translate([switch_spacing/2,switch_spacing/2,0])
        switch();

        translate([-switch_spacing/2-lower_button_width,switch_spacing/2,0])
        switch();
    
        translate([switch_spacing/2,-switch_spacing/2-lower_button_depth,0])
        switch();
        
        translate([-switch_spacing/2-lower_button_width,-switch_spacing/2-lower_button_depth,0])
        switch();    
    }

    // BOX screw tubes
    for (x=[-led_outer_diameter/2,led_outer_diameter/2]) {
        for (y=[-led_outer_diameter/2,led_outer_diameter/2]) {
            translate([x,y,switch_tray_thickness])
            difference() {
                cylinder(r=screw_tube_outer_diameter/2,h=switch_tray_height);
                translate([0,0,-1])
                cylinder(r=screw_tube_diameter/2,h=switch_tray_height+2);
            }
        }
    }

    translate([switch_spacing/2,switch_spacing/2,0])
    switch_upper();

    translate([-switch_spacing/2-lower_button_width,switch_spacing/2,0])
    switch_upper();
    
    translate([switch_spacing/2,-switch_spacing/2-lower_button_depth,0])
    switch_upper();
    
    translate([-switch_spacing/2-lower_button_width,-switch_spacing/2-lower_button_depth,0])
    switch_upper();    
}

// BUTTONS
union() {
    for (x=[switch_spacing/2,-switch_spacing/2-lower_button_width]) {
        for (y=[switch_spacing/2,-switch_spacing/2-lower_button_depth]) {

            translate([0, 0, interior_height-lower_button_thickness]) {
                translate([x, y, 0])
                cube([lower_button_width, lower_button_depth, lower_button_thickness]);

                translate([0, 0, lower_button_thickness])
                intersection()
                {
                    translate([x+button_tolarance, y+button_tolarance, 0])
                    cube([lower_button_width-button_tolarance*2, lower_button_depth-button_tolarance*2, upper_button_thickness]);                    
                    cylinder(r=led_inner_diameter/2 - button_tolarance,h=upper_button_thickness+2);
                }

            }
        }
    }
}

