"""
blender_n_noid_ui.py

Blender add-on style script that creates an interactive "n-noid" generator with a live UI in the N-panel.
Move sliders in the panel and the mesh updates immediately (the script updates the existing mesh rather than
recreating a new object, so changes are instant and non-destructive).

Install / use:
  1. In Blender open Scripting > New Text, paste this whole file and click "Run Script" OR save it as a .py and install as an add-on.
  2. In the 3D Viewport press N to open the side panel and look for the 'N-Noid' tab.
  3. Click "Create/Update N-Noid" to create the mesh the first time. Afterwards changing sliders updates the mesh live.

Notes:
 - The script stores parameters in scene.n_noid_props so they persist for the .blend file.
 - Updating many subdivisions while dragging may be slow; increase/decrease u_segments and v_segments more
   deliberately for heavy meshes.
 - This is still a parametric approximation, not an exact minimal-surface solver.

Author: Generated with ChatGPT
"""

bl_info = {
    "name": "N-Noid Generator (Live UI)",
    "author": "ChatGPT",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > N-Noid",
    "description": "Interactive n-noid / multi-catenoid generator with live parameter sliders",
    "category": "Add Mesh",
}

import bpy
import bmesh
from math import sin, cos, pi, exp, cosh

# -------------------------
# Parametric surface logic
# -------------------------

def parametric_point(u, v, p):
    n = p.n
    scale = p.scale
    bump = p.bump_strength
    decay = p.bump_decay
    axial = p.axial_strength

    base_r = cosh(v)
    envelope = exp(- (v*v) / (decay*decay))
    radial_mod = 1.0 + bump * envelope * cos(n * u)
    axial_mod = axial * envelope * sin(n * u)

    r = base_r * radial_mod
    x = scale * r * cos(u)
    y = scale * r * sin(u)
    z = scale * (v + axial_mod)
    return (x, y, z)


def generate_grid_vertices(p):
    u_segs = max(4, int(p.u_segments))
    v_segs = max(2, int(p.v_segments))
    v_extent = float(p.v_extent)

    verts = []
    for j in range(v_segs + 1):
        v = -v_extent + 2.0 * v_extent * j / v_segs
        for i in range(u_segs):
            u = 2.0 * pi * i / u_segs
            verts.append(parametric_point(u, v, p))
    faces = []
    def idx(i, j):
        return j * u_segs + (i % u_segs)
    for j in range(v_segs):
        for i in range(u_segs):
            v0 = idx(i, j)
            v1 = idx(i + 1, j)
            v2 = idx(i + 1, j + 1)
            v3 = idx(i, j + 1)
            faces.append((v0, v1, v2, v3))
    return verts, faces


# -------------------------
# Mesh creation / update
# -------------------------

def ensure_object(context, name):
    """Return existing object with name or create empty mesh object placeholder."""
    if name in bpy.data.objects:
        return bpy.data.objects[name]
    mesh = bpy.data.meshes.new(name + '_mesh')
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    return obj


def build_or_update_mesh(obj, props):
    """Create or update the mesh geometry in-place so UI changes are immediate."""
    mesh = obj.data
    verts, faces = generate_grid_vertices(props)

    # replace geometry robustly
    mesh.clear_geometry()
    mesh.from_pydata(verts, [], faces)

    # smooth shading
    bm = bmesh.new()
    bm.from_mesh(mesh)
    for f in bm.faces:
        f.smooth = True
    # recalc normals robustly
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    # optional: ensure object has a subdivision modifier for smoothing
    sub = None
    for m in obj.modifiers:
        if m.type == 'SUBSURF' and m.name == 'NNoid_Subdiv':
            sub = m
            break
    if sub is None:
        sub = obj.modifiers.new(name='NNoid_Subdiv', type='SUBSURF')
        sub.levels = 2
        sub.render_levels = 2

    # flip normals if requested
    if props.flip_normals:
        # use bmesh flip as safe method
        bm2 = bmesh.new()
        bm2.from_mesh(mesh)
        for f in bm2.faces:
            f.normal_flip()
        bm2.to_mesh(mesh)
        bm2.free()


# -------------------------
# Property group with update callbacks
# -------------------------
class NNoidProperties(bpy.types.PropertyGroup):
    def _update(self, context):
        # called whenever a property changes; update the existing mesh if present
        name = "n_noid_live"
        obj = bpy.data.objects.get(name)
        if obj is None:
            return
        # throttle heavy rebuilds for segment properties: only update if segments are moderate
        try:
            build_or_update_mesh(obj, self)
        except Exception as e:
            # avoid crashing UI; print to system console for debug
            print("N-Noid update error:", e)

    n: bpy.props.IntProperty(name="N", default=3, min=1, max=24, update=_update)
    u_segments: bpy.props.IntProperty(name="U Segs", default=160, min=8, max=1024, update=_update)
    v_segments: bpy.props.IntProperty(name="V Segs", default=80, min=4, max=512, update=_update)
    v_extent: bpy.props.FloatProperty(name="V Extent", default=2.5, min=0.1, max=10.0, update=_update)
    scale: bpy.props.FloatProperty(name="Scale", default=1.0, min=0.01, max=10.0, update=_update)
    bump_strength: bpy.props.FloatProperty(name="Bump Strength", default=0.6, min=0.0, max=2.0, update=_update)
    bump_decay: bpy.props.FloatProperty(name="Bump Decay", default=1.8, min=0.1, max=10.0, update=_update)
    axial_strength: bpy.props.FloatProperty(name="Axial Strength", default=0.25, min=0.0, max=2.0, update=_update)
    flip_normals: bpy.props.BoolProperty(name="Flip Normals", default=False, update=_update)


# -------------------------
# Operators & Panel
# -------------------------
class NNOID_OT_create_update(bpy.types.Operator):
    """Create or update the N-Noid mesh"""
    bl_idname = "nnoid.create_update"
    bl_label = "Create/Update N-Noid"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.n_noid_props
        name = "n_noid_live"
        obj = ensure_object(context, name)
        build_or_update_mesh(obj, props)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class NNOID_OT_remove(bpy.types.Operator):
    """Remove the N-Noid object and reset properties"""
    bl_idname = "nnoid.remove"
    bl_label = "Remove N-Noid"

    def execute(self, context):
        name = "n_noid_live"
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        return {'FINISHED'}


class NNOID_PT_panel(bpy.types.Panel):
    bl_label = "N-Noid Generator"
    bl_idname = "NNOID_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'N-Noid'

    def draw(self, context):
        layout = self.layout
        props = context.scene.n_noid_props

        col = layout.column()
        col.operator('nnoid.create_update', icon='MESH_TORUS')
        col.operator('nnoid.remove', icon='X')
        col.separator()

        col.prop(props, 'n')
        col.prop(props, 'u_segments')
        col.prop(props, 'v_segments')
        col.prop(props, 'v_extent')
        col.prop(props, 'scale')
        col.separator()
        col.prop(props, 'bump_strength')
        col.prop(props, 'bump_decay')
        col.prop(props, 'axial_strength')
        col.prop(props, 'flip_normals')


# -------------------------
# Registration
# -------------------------
classes = (
    NNoidProperties,
    NNOID_OT_create_update,
    NNOID_OT_remove,
    NNOID_PT_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.n_noid_props = bpy.props.PointerProperty(type=NNoidProperties)


def unregister():
    if hasattr(bpy.types.Scene, 'n_noid_props'):
        del bpy.types.Scene.n_noid_props
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == '__main__':
    register()
