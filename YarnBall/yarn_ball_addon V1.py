"""
Yarn Ball generator -- interactive add-on version
----------------------------------------------------
Same non-self-intersecting winding scheme as before (monotonically
growing radius across many pole-to-pole passes, golden-angle phase
offset between passes), now wrapped as a small add-on with:

  - All parameters exposed as sliders in the 3D Viewport sidebar
    (press N, look for the "Yarn Ball" tab).
  - A "Generate Yarn Ball" button that (re)builds the object in place
    -- no need to re-run or edit the script each time.
  - An optional fly-away fiber pass: short, thin, tapered hair-like
    splines sprouting outward near the surface, for a genuinely fuzzy
    look on top of the main strand's organic wobble.
  - Feedback via self.report(), which shows up in Blender's status
    bar and Info log -- no terminal/console needed.

Install:
    Edit > Preferences > Add-ons > Install... and pick this file,
    then enable it. (Or just paste into the Scripting workspace and
    hit Run Script -- it registers itself for the current session.)
"""

import math
import random
import bpy
from mathutils import Vector, noise as bnoise

bl_info = {
    "name": "Yarn Ball Generator",
    "author": "Claudio",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Yarn Ball",
    "description": "Generates a filled, non-self-intersecting yarn-ball curve with adjustable noise and fly-away fibers",
    "category": "Add Curve",
}

GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))  # ~2.39996 rad


# ---------------------------------------------------------------------------
# Core math (pure functions, no globals -- everything comes from props)
# ---------------------------------------------------------------------------

def inter_pass_gap(core_radius, outer_radius, num_passes):
    return (outer_radius - core_radius) / num_passes


def same_pass_gap(radius, wraps_per_pass):
    return radius * math.pi / wraps_per_pass


def safe_wobble_amplitude(radius, core_radius, outer_radius, num_passes,
                           wraps_per_pass, margin_factor, bevel_depth):
    smallest_gap = min(
        same_pass_gap(radius, wraps_per_pass),
        inter_pass_gap(core_radius, outer_radius, num_passes),
    )
    return max(smallest_gap * margin_factor - bevel_depth, 0.0)


def build_main_strand(p):
    """Returns a list of Vector points for the main yarn strand."""
    total_points = p.num_passes * p.points_per_pass
    seed_offset = Vector((p.seed * 17.0, p.seed * 31.0, p.seed * 53.0))
    points = []

    for i in range(total_points):
        T = i / (total_points - 1)
        pass_pos = T * p.num_passes
        pass_index = min(int(pass_pos), p.num_passes - 1)
        u = pass_pos - pass_index

        if pass_index % 2 == 0:
            phi = u * math.pi
        else:
            phi = math.pi - u * math.pi

        theta = 2.0 * p.wraps_per_pass * phi + pass_index * GOLDEN_ANGLE

        direction = Vector((
            math.sin(phi) * math.cos(theta),
            math.sin(phi) * math.sin(theta),
            math.cos(phi),
        ))

        radius_base = p.core_radius + (p.outer_radius - p.core_radius) * T

        sample_pos = direction * p.noise_scale + seed_offset
        wobble = bnoise.turbulence(sample_pos, p.noise_detail, False) * 2.0 - 1.0
        amplitude = safe_wobble_amplitude(
            radius_base, p.core_radius, p.outer_radius, p.num_passes,
            p.wraps_per_pass, p.margin_factor, p.bevel_depth,
        ) * p.noise_strength

        radius = radius_base + wobble * amplitude
        points.append(direction * radius)

    return points


def build_fibers(main_points, p):
    """Returns a list of (points, radii) tuples, one per fly-away fiber."""
    if p.fiber_count <= 0:
        return []

    rng = random.Random(p.seed * 9973 + 1)
    fibers = []
    total_points = len(main_points)

    for i in range(p.fiber_count):
        # Bias sample toward the outer surface (t -> 1) via an exponent < 1.
        t_sample = rng.random() ** (1.0 / (1.0 + p.fiber_surface_bias * 5.0))
        index = int(t_sample * (total_points - 1))
        base = main_points[index]

        outward = base.normalized() if base.length > 1e-6 else Vector((0, 0, 1))
        tilt = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        direction = (outward + tilt * 0.4).normalized()

        length = p.fiber_length * (1.0 + (rng.random() - 0.5) * p.fiber_length_variation)
        n_pts = 5
        cur = base.copy()
        fiber_points = [cur.copy()]

        for j in range(1, n_pts):
            noise_pos = cur * 4.0 + Vector((i * 3.1, i * 5.7, i * 2.3))
            curl = Vector((
                bnoise.noise(noise_pos) - 0.5,
                bnoise.noise(noise_pos + Vector((7.3, 0, 0))) - 0.5,
                bnoise.noise(noise_pos + Vector((0, 7.3, 0))) - 0.5,
            ))
            step_dir = (direction + curl * p.fiber_curl).normalized()
            cur = cur + step_dir * (length / (n_pts - 1))
            fiber_points.append(cur.copy())

        radii = [1.0 - (k / (n_pts - 1)) for k in range(n_pts)]  # taper to a point
        radii = [r * p.fiber_thickness_ratio for r in radii]
        fibers.append((fiber_points, radii))

    return fibers


def build_curve_object(p):
    # Remove any previous object/data with the same name so re-running updates in place.
    old_obj = bpy.data.objects.get(p.object_name)
    if old_obj is not None:
        old_data = old_obj.data
        bpy.data.objects.remove(old_obj, do_unlink=True)
        if old_data is not None and old_data.users == 0:
            bpy.data.curves.remove(old_data)

    main_points = build_main_strand(p)

    curve_data = bpy.data.curves.new(p.object_name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = p.bevel_depth
    curve_data.bevel_resolution = 4
    curve_data.fill_mode = 'FULL'
    curve_data.resolution_u = 12

    main_spline = curve_data.splines.new('NURBS')
    main_spline.points.add(len(main_points) - 1)
    for point, coord in zip(main_spline.points, main_points):
        point.co = (coord.x, coord.y, coord.z, 1.0)
        point.radius = 1.0
    main_spline.use_endpoint_u = True
    main_spline.use_cyclic_u = False
    main_spline.order_u = 4

    if p.generate_fibers:
        for fiber_points, radii in build_fibers(main_points, p):
            spline = curve_data.splines.new('POLY')
            spline.points.add(len(fiber_points) - 1)
            for point, coord, rad in zip(spline.points, fiber_points, radii):
                point.co = (coord.x, coord.y, coord.z, 1.0)
                point.radius = rad

    obj = bpy.data.objects.new(p.object_name, curve_data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj, main_points


# ---------------------------------------------------------------------------
# Property group (the sliders)
# ---------------------------------------------------------------------------

class YarnBallProperties(bpy.types.PropertyGroup):
    object_name: bpy.props.StringProperty(name="Name", default="Yarn Ball")

    core_radius: bpy.props.FloatProperty(name="Core Radius", default=0.15, min=0.0, soft_max=1.0)
    outer_radius: bpy.props.FloatProperty(name="Outer Radius", default=2.0, min=0.01, soft_max=10.0)

    num_passes: bpy.props.IntProperty(name="Passes", default=30, min=2, soft_max=200)
    wraps_per_pass: bpy.props.IntProperty(name="Wraps / Pass", default=6, min=1, soft_max=30)
    points_per_pass: bpy.props.IntProperty(name="Points / Pass", default=80, min=4, soft_max=300)

    noise_scale: bpy.props.FloatProperty(name="Noise Scale", default=1.5, min=0.0, soft_max=10.0)
    noise_detail: bpy.props.IntProperty(name="Noise Detail", default=3, min=1, max=8)
    noise_strength: bpy.props.FloatProperty(name="Noise Strength", default=1.0, min=0.0, soft_max=3.0)
    margin_factor: bpy.props.FloatProperty(name="Margin Factor", default=0.5, min=0.0, max=0.95)
    seed: bpy.props.IntProperty(name="Seed", default=2)
    bevel_depth: bpy.props.FloatProperty(name="Thread Thickness", default=0.015, min=0.0001, soft_max=0.2)

    generate_fibers: bpy.props.BoolProperty(name="Fly-Away Fibers", default=True)
    fiber_count: bpy.props.IntProperty(name="Fiber Count", default=150, min=0, soft_max=2000)
    fiber_length: bpy.props.FloatProperty(name="Fiber Length", default=0.15, min=0.0, soft_max=1.0)
    fiber_length_variation: bpy.props.FloatProperty(name="Length Variation", default=0.5, min=0.0, max=1.0)
    fiber_thickness_ratio: bpy.props.FloatProperty(name="Fiber Thickness", default=0.4, min=0.0, max=1.0)
    fiber_curl: bpy.props.FloatProperty(name="Fiber Curl", default=0.6, min=0.0, soft_max=2.0)
    fiber_surface_bias: bpy.props.FloatProperty(name="Surface Bias", default=0.8, min=0.0, max=1.0)


# ---------------------------------------------------------------------------
# Operator (the button)
# ---------------------------------------------------------------------------

class CURVE_OT_generate_yarn_ball(bpy.types.Operator):
    bl_idname = "curve.generate_yarn_ball"
    bl_label = "Generate Yarn Ball"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        p = context.scene.yarn_ball_props
        obj, main_points = build_curve_object(p)

        gap_between = inter_pass_gap(p.core_radius, p.outer_radius, p.num_passes)
        amp_outer = safe_wobble_amplitude(
            p.outer_radius, p.core_radius, p.outer_radius, p.num_passes,
            p.wraps_per_pass, p.margin_factor, p.bevel_depth,
        ) * p.noise_strength

        msg = (
            f"'{obj.name}' built: {p.num_passes} passes, inter-pass gap "
            f"{gap_between:.4f}, wobble amplitude {amp_outer:.4f} "
            f"(thread thickness {p.bevel_depth:.4f})"
        )
        level = 'WARNING' if amp_outer < p.bevel_depth * 0.5 else 'INFO'
        self.report({level}, msg)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel (the sidebar UI)
# ---------------------------------------------------------------------------

class VIEW3D_PT_yarn_ball(bpy.types.Panel):
    bl_label = "Yarn Ball"
    bl_idname = "VIEW3D_PT_yarn_ball"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Yarn Ball"

    def draw(self, context):
        layout = self.layout
        p = context.scene.yarn_ball_props

        layout.prop(p, "object_name")

        box = layout.box()
        box.label(text="Shape")
        box.prop(p, "core_radius")
        box.prop(p, "outer_radius")

        box = layout.box()
        box.label(text="Winding")
        box.prop(p, "num_passes")
        box.prop(p, "wraps_per_pass")
        box.prop(p, "points_per_pass")

        box = layout.box()
        box.label(text="Noise / Shag")
        box.prop(p, "noise_scale")
        box.prop(p, "noise_detail")
        box.prop(p, "noise_strength")
        box.prop(p, "margin_factor")
        box.prop(p, "seed")
        box.prop(p, "bevel_depth")

        box = layout.box()
        box.label(text="Fly-Away Fibers")
        box.prop(p, "generate_fibers")
        col = box.column()
        col.enabled = p.generate_fibers
        col.prop(p, "fiber_count")
        col.prop(p, "fiber_length")
        col.prop(p, "fiber_length_variation")
        col.prop(p, "fiber_thickness_ratio")
        col.prop(p, "fiber_curl")
        col.prop(p, "fiber_surface_bias")

        layout.separator()
        layout.operator("curve.generate_yarn_ball", icon='CURVE_DATA')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    YarnBallProperties,
    CURVE_OT_generate_yarn_ball,
    VIEW3D_PT_yarn_ball,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.yarn_ball_props = bpy.props.PointerProperty(type=YarnBallProperties)


def unregister():
    del bpy.types.Scene.yarn_ball_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
