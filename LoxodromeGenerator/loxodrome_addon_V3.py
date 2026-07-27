bl_info = {
    "name": "Loxodrome Generator",
    "author": "Claudio",
    "version": (1, 0, 0),
    "blender": (4, 1, 0),
    "location": "View3D > N-Panel > Loxodrome",
    "description": "Generate loxodrome curves with stereographic projection, adjustable via N-panel",
    "category": "Add Curve",
}

import bpy
import math
import random
import colorsys
from mathutils import Vector, Matrix
from bpy.props import (
    FloatProperty, IntProperty, BoolProperty, EnumProperty, StringProperty
)
from bpy.types import PropertyGroup, Operator, Panel


# =========================================================
# CORE GENERATION LOGIC
# =========================================================

def get_or_create_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def create_curve_object(points, name, collection, s):
    if len(points) < 2:
        return None

    curve_data = bpy.data.curves.new(name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = s.curve_resolution_u
    curve_data.bevel_depth = s.curve_bevel_depth
    curve_data.bevel_resolution = s.curve_bevel_resolution
    curve_data.fill_mode = s.curve_fill_mode

    spline = curve_data.splines.new(s.curve_type)
    spline.points.add(len(points) - 1)
    for i, p in enumerate(points):
        spline.points[i].co = (p.x, p.y, p.z, 1.0)

    if s.curve_type == 'NURBS':
        spline.use_endpoint_u = True

    obj = bpy.data.objects.new(name, curve_data)
    collection.objects.link(obj)

    if s.shade_smooth and s.curve_bevel_depth > 0:
        obj.data.splines[0].use_smooth = True

    return obj


def random_vivid_color(rng):
    """A random, vivid RGB color (high saturation/value so curves stay readable)."""
    hue = rng.random()
    sat = rng.uniform(0.6, 1.0)
    val = rng.uniform(0.8, 1.0)
    return colorsys.hsv_to_rgb(hue, sat, val)


def assign_color(obj, rgb, name):
    """Give the curve a viewport object-color AND a matching material,
    so it shows up in both Solid/Object-color mode and Material Preview/Rendered."""
    r, g, b = rgb
    obj.color = (r, g, b, 1.0)

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    mat.diffuse_color = (r, g, b, 1.0)

    obj.data.materials.append(mat)


def create_loxodrome_and_projection(phi, index, collection, s, rng=None):
    points_loxo = []
    points_proj = []

    rot_x = Matrix.Rotation(phi, 4, 'X')

    for i in range(s.steps):
        t = -s.t_range + (i / s.steps) * (2 * s.t_range)

        denom = math.sqrt(1 + (s.a * t) ** 2)
        v = Vector((math.sin(t) / denom, -s.a * t / denom, -math.cos(t) / denom))

        v_rot = rot_x @ v
        points_loxo.append(v_rot)

        if v_rot.z < s.z_cap:
            r = s.r_scale / (1.0 - v_rot.z)
            points_proj.append(Vector((r * v_rot.x, r * v_rot.y, s.proj_plane_z)))

    loxo_obj = create_curve_object(points_loxo, f"Loxodrome_{index}", collection, s)
    proj_obj = create_curve_object(points_proj, f"Projection_{index}", collection, s)

    if s.use_random_color and rng is not None:
        rgb = random_vivid_color(rng)
        if loxo_obj:
            assign_color(loxo_obj, rgb, f"Loxo_Color_{index}")
        if proj_obj:
            assign_color(proj_obj, rgb, f"Loxo_Color_{index}")


def create_helper_objects(s):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=s.sphere_radius, segments=s.sphere_segments, ring_count=s.sphere_rings
    )
    sphere_obj = bpy.context.active_object

    bpy.ops.mesh.primitive_plane_add(size=s.plane_size, location=(0, 0, s.proj_plane_z))
    plane_obj = bpy.context.active_object

    return [sphere_obj, plane_obj]


def remove_objects(objects):
    for obj in objects:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and data.users == 0 and isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)


def clear_previous_generation(collection):
    for obj in list(collection.objects):
        if obj.name.startswith("Loxodrome_") or obj.name.startswith("Projection_"):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                bpy.data.curves.remove(data)


# =========================================================
# PROPERTY GROUP (drives the N-panel)
# =========================================================

class LOXO_PG_Settings(PropertyGroup):
    # --- Shape ---
    a: FloatProperty(name="Tightness (a)", default=0.25, min=0.001, max=10.0,
                      description="Tightness of the loxodrome spiral")
    steps: IntProperty(name="Steps", default=2000, min=10, max=20000,
                        description="Number of points along the line")
    t_range: FloatProperty(name="T Range", default=100.0, min=1.0, max=1000.0,
                            description="Curve parameter runs from -T to +T")
    phi_steps: IntProperty(name="Phi Copies", default=12, min=1, max=200,
                            description="Number of rotated copies")
    phi_range: FloatProperty(name="Phi Range", default=math.pi, min=0.0, max=2 * math.pi,
                              subtype='ANGLE',
                              description="Angle range across which copies are spread")

    # --- Projection ---
    z_cap: FloatProperty(name="Z Cap", default=0.99, min=0.5, max=0.9999,
                          description="Points above this z are dropped near the pole")
    r_scale: FloatProperty(name="R Scale", default=1.6, min=0.01, max=20.0,
                            description="Scale factor in r = R_scale / (1 - z)")
    proj_plane_z: FloatProperty(name="Projection Plane Z", default=-1.0, min=-50.0, max=50.0)

    # --- Helpers ---
    sphere_radius: FloatProperty(name="Sphere Radius", default=0.99, min=0.01, max=10.0)
    sphere_segments: IntProperty(name="Sphere Segments", default=32, min=3, max=256)
    sphere_rings: IntProperty(name="Sphere Rings", default=16, min=3, max=256)
    plane_size: FloatProperty(name="Plane Size", default=8.0, min=0.1, max=200.0)
    keep_helpers: BoolProperty(name="Keep Sphere/Plane", default=False,
                                description="Keep the construction sphere and plane in the scene")

    # --- Curve look ---
    curve_type: EnumProperty(
        name="Curve Type",
        items=[('POLY', "Poly", "Passes exactly through every point"),
               ('NURBS', "NURBS", "Smooth interpolation, does not pass through points exactly")],
        default='POLY',
    )
    curve_bevel_depth: FloatProperty(name="Bevel Depth", default=0.01, min=0.0, max=5.0,
                                      description="Tube radius around the curve (0 = flat line)")
    curve_bevel_resolution: IntProperty(name="Bevel Resolution", default=4, min=0, max=32)
    curve_resolution_u: IntProperty(name="Resolution U", default=12, min=1, max=64)
    curve_fill_mode: EnumProperty(
        name="Fill Mode",
        items=[('FULL', "Full", ""), ('HALF', "Half", ""),
               ('FRONT', "Front", ""), ('BACK', "Back", "")],
        default='FULL',
    )
    shade_smooth: BoolProperty(name="Shade Smooth", default=True)

    # --- Color ---
    use_random_color: BoolProperty(
        name="Random Color", default=True,
        description="Give each loxodrome/projection pair a random vivid color "
                    "(visible in Solid 'Object Color' mode or Material Preview/Rendered)"
    )
    color_seed: IntProperty(
        name="Seed", default=0, min=0, max=999999,
        description="0 = a new random result every time you generate; "
                    "any other value reproduces the same colors"
    )

    # --- Organisation ---
    collection_name: StringProperty(name="Collection", default="Loxodromes")


# =========================================================
# OPERATORS
# =========================================================

class LOXO_OT_generate(Operator):
    bl_idname = "loxodrome.generate"
    bl_label = "Generate Loxodrome"
    bl_description = "Generate the loxodrome and projection curves with the current settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.loxodrome_settings
        collection = get_or_create_collection(s.collection_name)

        # remove curves from a previous run so re-generating doesn't pile up
        clear_previous_generation(collection)

        helpers = create_helper_objects(s)
        # helpers are created at cursor/origin by the ops above; make sure they land in our collection
        for h in helpers:
            for coll in list(h.users_collection):
                coll.objects.unlink(h)
            collection.objects.link(h)

        rng = random.Random(s.color_seed if s.color_seed != 0 else None)

        for i in range(s.phi_steps):
            phi = i * (s.phi_range / s.phi_steps) if s.phi_steps > 0 else 0
            create_loxodrome_and_projection(phi, i, collection, s, rng)

        if not s.keep_helpers:
            remove_objects(helpers)

        self.report({'INFO'}, f"Generated {s.phi_steps} loxodrome/projection pairs")
        return {'FINISHED'}


class LOXO_OT_reset(Operator):
    bl_idname = "loxodrome.reset_settings"
    bl_label = "Reset to Defaults"
    bl_description = "Reset all Loxodrome parameters back to their default values"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.loxodrome_settings
        for prop in s.bl_rna.properties:
            if prop.identifier == "rna_type":
                continue
            try:
                s.property_unset(prop.identifier)
            except Exception:
                pass
        self.report({'INFO'}, "Loxodrome settings reset to defaults")
        return {'FINISHED'}


def _merge_by_prefix(context, collection_name, prefix, merged_name):
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        return None, "Collection not found"

    objs = [o for o in collection.objects if o.name.startswith(prefix) and o.type == 'CURVE']
    if len(objs) < 2:
        return None, f"Need at least 2 '{prefix}*' curve objects to merge"

    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    context.view_layer.objects.active = objs[0]

    bpy.ops.object.join()

    merged_obj = context.view_layer.objects.active
    merged_obj.name = merged_name
    merged_obj.data.name = merged_name

    # The individual colors survive the join as per-spline materials, but a merged
    # object only has ONE "Object Color" left. Switch any visible 3D viewport to
    # show material colors instead, so the per-spline colors stay visible.
    if context.screen:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.color_type = 'MATERIAL'

    return merged_obj, None


class LOXO_OT_merge_loxodromes(Operator):
    bl_idname = "loxodrome.merge_loxodromes"
    bl_label = "Merge Loxodromes"
    bl_description = "Join all Loxodrome_* curves into a single curve object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.loxodrome_settings
        obj, err = _merge_by_prefix(context, s.collection_name, "Loxodrome_", "Loxodrome_merged")
        if err:
            self.report({'WARNING'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Merged into '{obj.name}' (colors preserved as materials — "
                               f"viewport switched to Material color)")
        return {'FINISHED'}


class LOXO_OT_merge_projections(Operator):
    bl_idname = "loxodrome.merge_projections"
    bl_label = "Merge Projections"
    bl_description = "Join all Projection_* curves into a single curve object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.loxodrome_settings
        obj, err = _merge_by_prefix(context, s.collection_name, "Projection_", "Projection_merged")
        if err:
            self.report({'WARNING'}, err)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Merged into '{obj.name}' (colors preserved as materials — "
                               f"viewport switched to Material color)")
        return {'FINISHED'}


# =========================================================
# N-PANEL
# =========================================================

class LOXO_PT_panel(Panel):
    bl_idname = "LOXO_PT_panel"
    bl_label = "Loxodrome Generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Loxodrome"

    def draw(self, context):
        layout = self.layout
        s = context.scene.loxodrome_settings

        box = layout.box()
        box.label(text="Shape")
        box.prop(s, "a")
        box.prop(s, "steps")
        box.prop(s, "t_range")
        box.prop(s, "phi_steps")
        box.prop(s, "phi_range")

        box = layout.box()
        box.label(text="Projection")
        box.prop(s, "z_cap")
        box.prop(s, "r_scale")
        box.prop(s, "proj_plane_z")

        box = layout.box()
        box.label(text="Helpers")
        box.prop(s, "keep_helpers")
        col = box.column()
        col.enabled = True
        col.prop(s, "sphere_radius")
        col.prop(s, "sphere_segments")
        col.prop(s, "sphere_rings")
        col.prop(s, "plane_size")

        box = layout.box()
        box.label(text="Curve Look")
        box.prop(s, "curve_type")
        box.prop(s, "curve_bevel_depth")
        box.prop(s, "curve_bevel_resolution")
        box.prop(s, "curve_resolution_u")
        box.prop(s, "curve_fill_mode")
        box.prop(s, "shade_smooth")

        box = layout.box()
        box.label(text="Color")
        box.prop(s, "use_random_color")
        col = box.column()
        col.enabled = s.use_random_color
        col.prop(s, "color_seed")

        box = layout.box()
        box.label(text="Organisation")
        box.prop(s, "collection_name")

        layout.separator()
        layout.operator("loxodrome.generate", icon='CURVE_DATA')
        layout.operator("loxodrome.reset_settings", icon='LOOP_BACK')

        layout.separator()
        row = layout.row(align=True)
        row.operator("loxodrome.merge_loxodromes", icon='LINKED')
        row.operator("loxodrome.merge_projections", icon='LINKED')


# =========================================================
# REGISTRATION
# =========================================================

classes = (
    LOXO_PG_Settings,
    LOXO_OT_generate,
    LOXO_OT_reset,
    LOXO_OT_merge_loxodromes,
    LOXO_OT_merge_projections,
    LOXO_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.loxodrome_settings = bpy.props.PointerProperty(type=LOXO_PG_Settings)


def unregister():
    del bpy.types.Scene.loxodrome_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
