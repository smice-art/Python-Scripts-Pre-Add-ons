bl_info = {
    "name": "Spherical Harmonic Generator",
    "author": "Claudio",
    "version": (2, 0, 0),
    "blender": (4, 1, 0),
    "location": "View3D > N-Panel > Harmonics",
    "description": "Generates a deformed sphere mesh from a real spherical harmonic Y(l,m)",
    "category": "Add Mesh",
}

import bpy
import bmesh
import math
from bpy.props import IntProperty, FloatProperty, BoolProperty, PointerProperty
from bpy.types import PropertyGroup, Operator, Panel
from bpy.app.handlers import persistent

OBJ_NAME = "SphericalHarmonic"
MESH_NAME = "SphericalHarmonic"


# --- Math Functions ---

def factorial(n):
    return math.factorial(n)


def associated_legendre(l, m, x):
    """
    General associated Legendre polynomial P(l,m)(x) via the standard
    stable recurrence (Condon-Shortley convention). Valid for any
    0 <= m <= l.
    """
    pmm = 1.0
    if m > 0:
        somx2 = math.sqrt((1.0 - x) * (1.0 + x))
        fact = 1.0
        for _ in range(1, m + 1):
            pmm *= -fact * somx2
            fact += 2.0

    if l == m:
        return pmm

    pmmp1 = x * (2 * m + 1) * pmm
    if l == m + 1:
        return pmmp1

    pll = 0.0
    for ll in range(m + 2, l + 1):
        pll = (x * (2 * ll - 1) * pmmp1 - (ll + m - 1) * pmm) / (ll - m)
        pmm = pmmp1
        pmmp1 = pll
    return pll


def get_harmonic_radius(theta, phi, l, m, base_r, strength):
    """ r = base_r + strength * Re[Y(l,m)] """
    norm = math.sqrt(
        ((2 * l + 1) * factorial(l - m)) / (4 * math.pi * factorial(l + m))
    )
    legendre = associated_legendre(l, m, math.cos(theta))
    y_val = norm * legendre * math.cos(m * phi)
    return base_r + (strength * y_val)


# --- Core generation logic ---

def build_harmonic_mesh(scene):
    """
    Rebuild the mesh geometry only - no selection/active-object changes.
    Safe to call from a frame-change handler during playback or rendering,
    where touching selection state would be disruptive.
    """
    settings = scene.spherical_harmonic_settings

    L = settings.l
    M = min(settings.m, L)  # M > L is undefined for the recurrence, so clamp
    RESOLUTION = settings.resolution
    BASE_R = settings.base_r
    STRENGTH = settings.strength
    SCALE = settings.scale

    # Reuse existing object/mesh if present, so lights/camera/materials
    # aren't disturbed on every regeneration.
    obj = bpy.data.objects.get(OBJ_NAME)
    if obj is None:
        mesh_data = bpy.data.meshes.new(MESH_NAME)
        obj = bpy.data.objects.new(OBJ_NAME, mesh_data)
        scene.collection.objects.link(obj)
    else:
        mesh_data = obj.data
        mesh_data.clear_geometry()

    bm = bmesh.new()

    for i in range(RESOLUTION + 1):
        theta = i * math.pi / RESOLUTION
        for j in range(RESOLUTION + 1):
            phi = j * 2 * math.pi / RESOLUTION

            r = get_harmonic_radius(theta, phi, L, M, BASE_R, STRENGTH)

            x = r * math.sin(theta) * math.cos(phi)
            y = r * math.sin(theta) * math.sin(phi)
            z = r * math.cos(theta)

            bm.verts.new((x * SCALE, y * SCALE, z * SCALE))

    bm.verts.ensure_lookup_table()
    stride = RESOLUTION + 1
    for i in range(RESOLUTION):
        for j in range(RESOLUTION):
            v1 = bm.verts[i * stride + j]
            v2 = bm.verts[(i + 1) * stride + j]
            v3 = bm.verts[(i + 1) * stride + (j + 1)]
            v4 = bm.verts[i * stride + (j + 1)]
            try:
                bm.faces.new((v1, v2, v3, v4))
            except ValueError:
                pass

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bm.to_mesh(mesh_data)
    bm.free()
    mesh_data.update()

    for poly in mesh_data.polygons:
        poly.use_smooth = True

    if not obj.data.materials:
        mat = bpy.data.materials.new(name="HarmonicMaterial")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1.0)
            bsdf.inputs["Metallic"].default_value = 0.2
            bsdf.inputs["Roughness"].default_value = 0.1
            if "Sheen Weight" in bsdf.inputs:
                bsdf.inputs["Sheen Weight"].default_value = 1.0
        obj.data.materials.append(mat)

    return obj


def generate_harmonic(context):
    """Used by the Generate button and slider Auto Update - also selects the object."""
    obj = build_harmonic_mesh(context.scene)
    context.view_layer.objects.active = obj
    obj.select_set(True)


def on_setting_changed(self, context):
    if self.auto_update:
        generate_harmonic(context)


@persistent
def frame_change_handler(scene, depsgraph):
    """
    Rebuilds the mesh from whatever 'strength' (or any other parameter)
    currently evaluates to on this frame. Needed because keyframed/F-curve
    driven property changes go through the depsgraph, not through the
    'update=' callback used for slider edits - so without this, the number
    animates but the mesh never rebuilds.
    """
    settings = scene.spherical_harmonic_settings
    if settings.animate_playback:
        build_harmonic_mesh(scene)


# --- Property Group ---

class SphericalHarmonicSettings(PropertyGroup):
    l: IntProperty(
        name="Degree (L)",
        description="Spherical harmonic degree l",
        default=8, min=0, max=40,
        update=on_setting_changed,
    )
    m: IntProperty(
        name="Order (M)",
        description="Spherical harmonic order m (clamped to L)",
        default=4, min=0, max=40,
        update=on_setting_changed,
    )
    resolution: IntProperty(
        name="Resolution",
        description="Grid subdivisions (N x N). High values + Auto Update can get slow",
        default=120, min=8, max=300,
        update=on_setting_changed,
    )
    base_r: FloatProperty(
        name="Base Radius",
        description="The constant offset in r = Base + Strength * Y",
        default=1.0, min=-10.0, max=10.0,
        update=on_setting_changed,
    )
    strength: FloatProperty(
        name="Strength",
        description="The coefficient in r = Base + Strength * Y",
        default=0.5, min=-5.0, max=5.0,
        update=on_setting_changed,
    )
    scale: FloatProperty(
        name="Scale",
        description="Uniform scale applied after the radius deformation",
        default=2.0, min=0.01, max=50.0,
        update=on_setting_changed,
    )
    auto_update: BoolProperty(
        name="Auto Update",
        description="Regenerate the mesh automatically whenever a parameter changes",
        default=False,
        update=on_setting_changed,
    )
    animate_playback: BoolProperty(
        name="Animate on Frame Change",
        description=(
            "Rebuild the mesh on every frame change during playback, scrubbing, "
            "and animation rendering - required for keyframed parameters "
            "(e.g. Strength) to actually deform the mesh"
        ),
        default=False,
    )


# --- Operator ---

class MESH_OT_generate_spherical_harmonic(Operator):
    bl_idname = "mesh.generate_spherical_harmonic"
    bl_label = "Generate Spherical Harmonic"
    bl_description = "Manually (re)generate the spherical harmonic mesh"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        generate_harmonic(context)
        return {'FINISHED'}


# --- Panel ---

class VIEW3D_PT_spherical_harmonic(Panel):
    bl_label = "Spherical Harmonic"
    bl_idname = "VIEW3D_PT_spherical_harmonic"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Harmonics"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.spherical_harmonic_settings

        col = layout.column(align=True)
        col.prop(settings, "l")
        col.prop(settings, "m")
        col.prop(settings, "resolution")

        layout.separator()
        box = layout.box()
        box.label(text="r = Base + Strength · Y(l,m)", icon='DRIVER')
        box.prop(settings, "base_r")
        box.prop(settings, "strength")

        layout.separator()
        layout.prop(settings, "scale")

        layout.separator()
        layout.prop(settings, "auto_update", toggle=True)
        layout.operator(
            "mesh.generate_spherical_harmonic",
            text="Generate",
            icon='MESH_UVSPHERE',
        )

        layout.separator()
        anim_box = layout.box()
        anim_box.label(text="Animation", icon='ARMATURE_DATA')
        anim_box.prop(settings, "animate_playback", toggle=True)
        col = anim_box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Keyframe any field above (hover + I),")
        col.label(text="then enable this to rebuild per frame.")


# --- Registration ---

classes = (
    SphericalHarmonicSettings,
    MESH_OT_generate_spherical_harmonic,
    VIEW3D_PT_spherical_harmonic,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.spherical_harmonic_settings = PointerProperty(
        type=SphericalHarmonicSettings
    )
    if frame_change_handler not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(frame_change_handler)


def unregister():
    if frame_change_handler in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(frame_change_handler)
    del bpy.types.Scene.spherical_harmonic_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
