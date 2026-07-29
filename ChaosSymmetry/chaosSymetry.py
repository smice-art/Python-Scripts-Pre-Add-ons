bl_info = {
    "name": "Symmetric Attractor Generator",
    "author": "claudio",
    "version": (1, 6),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar (N) > ChaosSymmetry",
    "description": "Generate iterative symmetric chaotic attractors as Bezier curves with custom material controls",
    "category": "Add Curve",
}

import bpy
import math
import cmath
import random
import colorsys
from math import log1p

# -----------------------
# Utility & iteration code (safe)
# -----------------------
tiny = 1e-14
max_abs = 1e6
bailout_abs = 1e7

def safe_pow(z, exponent):
    try:
        if z == 0:
            exp_re = exponent.real if isinstance(exponent, complex) else float(exponent)
            return complex(tiny) if exp_re < 0 else complex(0.0)
        if abs(z) > max_abs:
            z = (z / abs(z)) * max_abs
        return cmath.exp(exponent * cmath.log(z))
    except Exception:
        try:
            mag = abs(z)
            ang = math.atan2(z.imag, z.real)
            e_re = exponent.real if isinstance(exponent, complex) else float(exponent)
            mag_part = mag ** e_re if mag > 0 else 0.0
            angle_part = ang * e_re
            return complex(mag_part * math.cos(angle_part), mag_part * math.sin(angle_part))
        except Exception:
            return complex(tiny)

def attractor_iter(z, a0, a1, a2, a3, a4, n, m, global_map_scale, damping):
    if abs(z) < tiny:
        z = complex(tiny, 0.0)
    if abs(z) > max_abs:
        z = (z / abs(z)) * max_abs

    try:
        power_val = safe_pow(z, float(n) / float(m))
        re_term = power_val.real
    except Exception:
        re_term = (abs(z) ** (float(n)/float(m)))

    try:
        neg_exponent_value = - ( (float(n)) ** (1.0/float(m)) )
        neg_exp = safe_pow(z, neg_exponent_value)
    except Exception:
        neg_exp = 1.0 / (z + complex(tiny, tiny))

    z_next_raw = (a0 + a1 * z + a2 * re_term + a3 * 1j) * z + a4 * neg_exp
    z_next = global_map_scale * z_next_raw
    z_next = z_next / (1.0 + damping * abs(z_next))
    return z_next, z_next_raw

def generate_seeds(count, radius, grid=False):
    seeds = []
    if grid:
        side = int(math.sqrt(count))
        if side < 1: side = 1
        xs = [ (i / (side-1) * 2 - 1) for i in range(side) ] if side>1 else [0]
        ys = xs[:]
        for x in xs:
            for y in ys:
                seeds.append( complex(x*radius, y*radius) )
        return seeds[:count]
    else:
        for i in range(count):
            r = radius * (0.12 + 0.88 * random.random())
            theta = random.random() * 2 * math.pi
            jitter = 0.18 * (random.random()-0.5)
            seeds.append( complex(r * math.cos(theta) + jitter, r * math.sin(theta) + jitter) )
        return seeds

# -----------------------
# Material Generator
# -----------------------
MAT_NAME = "ChaosSymmetry_Material"

def create_or_update_random_material(obj):
    mat = bpy.data.materials.get(MAT_NAME)
    if not mat:
        mat = bpy.data.materials.new(name=MAT_NAME)
    
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Shader Nodes Setup
    tex_coord = nodes.new(type='ShaderNodeTexCoord')
    tex_coord.location = (-800, 0)

    vec_len = nodes.new(type='ShaderNodeVectorMath')
    vec_len.operation = 'LENGTH'
    vec_len.location = (-600, 0)

    scale_node = nodes.new(type='ShaderNodeMath')
    scale_node.operation = 'MULTIPLY'
    scale_node.inputs[1].default_value = 2.0
    scale_node.location = (-400, 0)

    ramp = nodes.new(type='ShaderNodeValToRGB')
    ramp.location = (-200, 0)
    ramp.color_ramp.interpolation = 'EASE'

    # Build Random Color Ramp
    elements = ramp.color_ramp.elements
    while len(elements) > 1:
        elements.remove(elements[-1])

    num_stops = random.randint(5, 8)
    for i in range(num_stops):
        pos = i / (num_stops - 1)
        if i == 0:
            elem = elements[0]
            elem.position = 0.0
        else:
            elem = elements.new(pos)

        hue = random.random()
        sat = random.uniform(0.75, 1.0)
        val = random.uniform(0.85, 1.0)
        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        elem.color = (r, g, b, 1.0)

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (100, 0)

    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (350, 0)

    # Link Nodes
    links.new(tex_coord.outputs['Object'], vec_len.inputs[0])
    links.new(vec_len.outputs['Value'], scale_node.inputs[0])
    links.new(scale_node.outputs['Value'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    if obj:
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat

    return mat

# -----------------------
# Curve creation / cleanup
# -----------------------
OBJ_NAME = "SymmetricAttractorObj"

def cleanup_previous():
    to_delete = [o for o in bpy.data.objects if o.name.startswith(OBJ_NAME)]
    for o in to_delete:
        try:
            bpy.data.objects.remove(o, do_unlink=True)
        except Exception:
            pass

def create_attractor_curve_from_props(context, props):
    a0 = props.a0
    a1 = props.a1
    a2 = props.a2
    a3 = props.a3
    a4 = props.a4
    n = props.n
    m = props.m
    iterations = props.iterations
    seed_count = props.seed_count
    seed_radius = props.seed_radius
    grid_mode = props.grid_mode

    vertical_scale = props.vertical_scale
    mag_scale = props.mag_scale
    global_scale = props.global_scale
    global_map_scale = props.global_map_scale
    damping = props.damping
    
    curve_res = props.curve_resolution
    bevel_depth = props.bevel_depth
    bevel_resolution = props.bevel_resolution

    seeds = generate_seeds(seed_count, seed_radius, grid_mode)

    curve_data = bpy.data.curves.new(name="SymmetricAttractorCurve", type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = curve_res

    for s_idx, seed in enumerate(seeds):
        z = seed
        coords = []
        
        for k in range(iterations):
            if not math.isfinite(z.real) or not math.isfinite(z.imag) or abs(z) > bailout_abs:
                break
            x = global_scale * z.real
            y = global_scale * z.imag
            zcoord = k * vertical_scale + math.log1p(abs(z)) * mag_scale
            zcoord *= global_scale
            coords.append((x, y, zcoord))
            z, _ = attractor_iter(z, a0, a1, a2, a3, a4, n, m, global_map_scale, damping)

        if len(coords) > 0:
            spline = curve_data.splines.new(type='BEZIER')
            spline.bezier_points.add(len(coords) - 1)
            
            for i, co in enumerate(coords):
                bp = spline.bezier_points[i]
                bp.co = co
                bp.handle_left_type = 'AUTO'
                bp.handle_right_type = 'AUTO'

    curve_obj = bpy.data.objects.new(OBJ_NAME, curve_data)
    context.collection.objects.link(curve_obj)

    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = bevel_resolution

    # Reassign existing material if present
    existing_mat = bpy.data.materials.get(MAT_NAME)
    if existing_mat:
        curve_obj.data.materials.append(existing_mat)

    return curve_obj

# -----------------------
# Property group + update
# -----------------------
def rebuild_from_scene(context):
    props = context.scene.chaos_symmetry_settings
    cleanup_previous()
    create_attractor_curve_from_props(context, props)

def update_attractor(self, context):
    if context is None: return
    props = context.scene.chaos_symmetry_settings
    if props.auto_update:
        try:
            rebuild_from_scene(context)
        except Exception as e:
            print("[ChaosSymmetry] Update error:", e)

class ChaosSymmetrySettings(bpy.types.PropertyGroup):
    a0: bpy.props.FloatProperty(name="a0", default=0.12, update=update_attractor)
    a1: bpy.props.FloatProperty(name="a1", default=0.28, update=update_attractor)
    a2: bpy.props.FloatProperty(name="a2", default=-0.18, update=update_attractor)
    a3: bpy.props.FloatProperty(name="a3", default=0.35, update=update_attractor)
    a4: bpy.props.FloatProperty(name="a4", default=0.0, update=update_attractor)

    n: bpy.props.IntProperty(name="n", default=3, min=1, update=update_attractor)
    m: bpy.props.IntProperty(name="m", default=2, min=1, update=update_attractor)

    iterations: bpy.props.IntProperty(name="iterations", default=32, min=1, max=300, update=update_attractor)
    seed_count: bpy.props.IntProperty(name="seed_count", default=64, min=1, max=2000, update=update_attractor)
    seed_radius: bpy.props.FloatProperty(name="seed_radius", default=0.4, min=0.0, update=update_attractor)
    grid_mode: bpy.props.BoolProperty(name="grid_mode", default=False, update=update_attractor)

    vertical_scale: bpy.props.FloatProperty(name="vertical_scale", default=0.035, update=update_attractor)
    mag_scale: bpy.props.FloatProperty(name="mag_scale", default=0.06, update=update_attractor)
    global_scale: bpy.props.FloatProperty(name="global_scale", default=1.0, update=update_attractor)
    global_map_scale: bpy.props.FloatProperty(name="global_map_scale", default=0.16, min=0.001, max=15.5, update=update_attractor)
    damping: bpy.props.FloatProperty(name="damping", default=0.10, min=0.0, max=2.0, update=update_attractor)

    curve_resolution: bpy.props.IntProperty(
        name="Resolution U", 
        default=24, 
        min=1, 
        max=128, 
        description="Resolution/smoothness of the generated curve",
        update=update_attractor
    )

    bevel_depth: bpy.props.FloatProperty(
        name="Bevel Depth", 
        default=0.005, 
        min=0.0, 
        soft_max=0.5,
        step=0.001, 
        description="Thickness of the curve bevel",
        update=update_attractor
    )
    bevel_resolution: bpy.props.IntProperty(
        name="Bevel Resolution", 
        default=2, 
        min=0, 
        max=32, 
        description="Resolution of the bevel geometry profile",
        update=update_attractor
    )

    auto_update: bpy.props.BoolProperty(name="Auto Update", default=False)

# -----------------------
# UI Panel & Operators
# -----------------------
class CHAOS_SYMMETRY_OT_rebuild(bpy.types.Operator):
    bl_idname = "chaos_symmetry.rebuild"
    bl_label = "Rebuild"
    bl_description = "Rebuild the symmetric attractor curve using current settings"
    def execute(self, context):
        try:
            rebuild_from_scene(context)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class CHAOS_SYMMETRY_OT_random_material(bpy.types.Operator):
    bl_idname = "chaos_symmetry.random_material"
    bl_label = "New Material"
    bl_description = "Generate a new random radial/concentric colorful material"
    def execute(self, context):
        obj = bpy.data.objects.get(OBJ_NAME)
        if not obj:
            rebuild_from_scene(context)
            obj = bpy.data.objects.get(OBJ_NAME)
        
        if obj:
            create_or_update_random_material(obj)
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Could not find or create attractor object")
            return {'CANCELLED'}

class CHAOS_SYMMETRY_PT_panel(bpy.types.Panel):
    bl_label = "Symmetric Attractor"
    bl_category = "ChaosSymmetry"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    def draw(self, context):
        layout = self.layout
        props = context.scene.chaos_symmetry_settings

        col = layout.column()
        col.prop(props, "auto_update")

        box = layout.box()
        box.label(text="Map parameters:")
        box.prop(props, "a0")
        box.prop(props, "a1")
        box.prop(props, "a2")
        box.prop(props, "a3")
        box.prop(props, "a4")

        box2 = layout.box()
        box2.label(text="Exponents / Iteration:")
        row = box2.row(align=True)
        row.prop(props, "n")
        row.prop(props, "m")
        box2.prop(props, "iterations")
        box2.prop(props, "seed_count")
        box2.prop(props, "seed_radius")
        box2.prop(props, "grid_mode")

        box3 = layout.box()
        box3.label(text="Visual / scaling:")
        box3.prop(props, "curve_resolution")
        box3.prop(props, "bevel_depth")
        box3.prop(props, "bevel_resolution")
        box3.prop(props, "vertical_scale")
        box3.prop(props, "mag_scale")
        box3.prop(props, "global_scale")
        box3.prop(props, "global_map_scale")
        box3.prop(props, "damping")

        box4 = layout.box()
        box4.label(text="Material / Shading:")
        box4.operator("chaos_symmetry.random_material", icon='COLOR')

        layout.operator("chaos_symmetry.rebuild", icon='CURVE_DATA')

# -----------------------
# Register
# -----------------------
classes = (
    ChaosSymmetrySettings,
    CHAOS_SYMMETRY_OT_rebuild,
    CHAOS_SYMMETRY_OT_random_material,
    CHAOS_SYMMETRY_PT_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.chaos_symmetry_settings = bpy.props.PointerProperty(type=ChaosSymmetrySettings)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    try:
        del bpy.types.Scene.chaos_symmetry_settings
    except Exception:
        pass

if __name__ == "__main__":
    register()
    print("Symmetric Attractor Generator registered. Open N-panel > ChaosSymmetry to use.")