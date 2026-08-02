bl_info = {
    "name": "Scherk Saddle Tower (2nd Scherk Surface)",
    "author": "Qwen",
    "version": (1, 2, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Scherk | Add menu",
    "description": "Generate the 2nd Scherk surface and its n-wing Saddle-Tower "
                   "generalisation, with bend/twist deformations and live update.",
    "category": "Add Mesh",
}

import bpy
import bmesh
import math
import time
import numpy as np
from bpy.props import (IntProperty, FloatProperty, BoolProperty,
                       EnumProperty, PointerProperty, StringProperty)
from bpy.types import Operator, Panel, PropertyGroup
from math import pi

# ----------------------------------------------------------------------------
# Marching-tetrahedra table (16 cases).  Tet edge order:
# e0=(0,1) e1=(0,2) e2=(0,3) e3=(1,2) e4=(1,3) e5=(2,3)
# Each entry = list of triangles, each triangle = 3 edge-indices.
# ----------------------------------------------------------------------------
TET_TABLE = [
    [],                          # 0
    [(0, 1, 2)],                 # 1
    [(0, 3, 4)],                 # 2
    [(1, 2, 4), (1, 4, 3)],      # 3
    [(1, 3, 5)],                 # 4
    [(0, 2, 5), (0, 5, 3)],      # 5
    [(0, 1, 5), (0, 5, 4)],      # 6
    [(2, 4, 5)],                 # 7
    [(2, 4, 5)],                 # 8
    [(0, 1, 5), (0, 5, 4)],      # 9
    [(0, 2, 5), (0, 5, 3)],      # 10
    [(1, 3, 5)],                 # 11
    [(1, 2, 4), (1, 4, 3)],      # 12
    [(0, 3, 4)],                 # 13
    [(0, 1, 2)],                 # 14
    [],                          # 15
]

# Cube -> 6 tetrahedra (Freudenthal / Kuhn triangulation, main diagonal 0-7)
TETS = [(0, 1, 3, 7), (0, 1, 5, 7), (0, 2, 3, 7),
        (0, 2, 6, 7), (0, 4, 5, 7), (0, 4, 6, 7)]

# local vertex l -> (di,dj,dk)
DI = np.array([(l & 1) for l in range(8)], dtype=np.int32)
DJ = np.array([(l >> 1 & 1) for l in range(8)], dtype=np.int32)
DK = np.array([(l >> 2 & 1) for l in range(8)], dtype=np.int32)

# ----------------------------------------------------------------------------
# Implicit field  F = amplitude * H_n(x,y) - sin(z + phase)
# EXACT  : H = sinh(x) sinh(y)            (true minimal surface, 4 wings)
# GENERAL: H = Im((x + i y)^n), n=wings/2 (2n-wing saddle tower)
# ----------------------------------------------------------------------------
def eval_field(X, Y, Z, mode, wings, amplitude, phase):
    if mode == 'EXACT':
        H = np.sinh(X) * np.sinh(Y)
    else:
        n = max(1, wings // 2)
        H = ((X + 1j * Y) ** n).imag
        H = np.clip(H, -1e8, 1e8)
    return amplitude * H - np.sin(Z + phase)

def eval_grad(cx, cy, cz, mode, wings, amplitude, phase):
    if mode == 'EXACT':
        gx = amplitude * np.cosh(cx) * np.sinh(cy)
        gy = amplitude * np.sinh(cx) * np.cosh(cy)
    else:
        n = max(1, wings // 2)
        Wp = n * ((cx + 1j * cy) ** (n - 1))
        gx = amplitude * Wp.imag
        gy = amplitude * Wp.real
    gz = -amplitude * np.cos(cz + phase)
    return gx, gy, gz

# ----------------------------------------------------------------------------
# Isosurface extraction (marching tetrahedra) at level 0
# ----------------------------------------------------------------------------
def extract_isosurface(xs, ys, zs, F, s):
    nx, ny, nz = F.shape
    z_len = s.segments * 2.0 * pi
    
    c = [
        F[:-1, :-1, :-1], F[1:, :-1, :-1], F[:-1, 1:, :-1], F[1:, 1:, :-1],
        F[:-1, :-1, 1:],  F[1:, :-1, 1:],  F[:-1, 1:, 1:],  F[1:, 1:, 1:],
    ]
    stack = np.stack(c, axis=0)
    active = (stack.min(axis=0) <= 0.0) & (stack.max(axis=0) >= 0.0)
    ii, jj, kk = np.nonzero(active)
    
    verts = []
    faces = []
    vmap = {}
    nxy = nx * ny
    
    DI_l = DI.tolist(); DJ_l = DJ.tolist(); DK_l = DK.tolist()
    
    for idx in range(ii.size):
        i = int(ii[idx]); j = int(jj[idx]); k = int(kk[idx])
        
        VL = (c[0][i, j, k], c[1][i, j, k], c[2][i, j, k], c[3][i, j, k],
              c[4][i, j, k], c[5][i, j, k], c[6][i, j, k], c[7][i, j, k])
        PL = ((xs[i + DI_l[0]], ys[j + DJ_l[0]], zs[k + DK_l[0]]),
              (xs[i + DI_l[1]], ys[j + DJ_l[1]], zs[k + DK_l[1]]),
              (xs[i + DI_l[2]], ys[j + DJ_l[2]], zs[k + DK_l[2]]),
              (xs[i + DI_l[3]], ys[j + DJ_l[3]], zs[k + DK_l[3]]),
              (xs[i + DI_l[4]], ys[j + DJ_l[4]], zs[k + DK_l[4]]),
              (xs[i + DI_l[5]], ys[j + DJ_l[5]], zs[k + DK_l[5]]),
              (xs[i + DI_l[6]], ys[j + DJ_l[6]], zs[k + DK_l[6]]),
              (xs[i + DI_l[7]], ys[j + DJ_l[7]], zs[k + DK_l[7]]))
        GI = (i + DI_l[0] + (j + DJ_l[0]) * nx + (k + DK_l[0]) * nxy,
              i + DI_l[1] + (j + DJ_l[1]) * nx + (k + DK_l[1]) * nxy,
              i + DI_l[2] + (j + DJ_l[2]) * nx + (k + DK_l[2]) * nxy,
              i + DI_l[3] + (j + DJ_l[3]) * nx + (k + DK_l[3]) * nxy,
              i + DI_l[4] + (j + DJ_l[4]) * nx + (k + DK_l[4]) * nxy,
              i + DI_l[5] + (j + DJ_l[5]) * nx + (k + DK_l[5]) * nxy,
              i + DI_l[6] + (j + DJ_l[6]) * nx + (k + DK_l[6]) * nxy,
              i + DI_l[7] + (j + DJ_l[7]) * nx + (k + DK_l[7]) * nxy)
              
        for (a, b, cc, d) in TETS:
            va, vb, vc, vd = VL[a], VL[b], VL[cc], VL[d]
            mask = (1 if va > 0 else 0) | (2 if vb > 0 else 0) | \
                   (4 if vc > 0 else 0) | (8 if vd > 0 else 0)
            tris = TET_TABLE[mask]
            if not tris:
                continue
                
            te = ((a, b), (a, cc), (a, d), (b, cc), (b, d), (cc, d))
            for tri in tris:
                fv = []
                for e in tri:
                    l1, l2 = te[e]
                    g1, g2 = GI[l1], GI[l2]
                    key = (g1, g2) if g1 < g2 else (g2, g1)
                    vi = vmap.get(key)
                    if vi is None:
                        v1 = VL[l1]; v2 = VL[l2]
                        t = v1 / (v1 - v2)
                        p1 = PL[l1]; p2 = PL[l2]
                        verts.append((p1[0] + t * (p2[0] - p1[0]),
                                      p1[1] + t * (p2[1] - p1[1]),
                                      p1[2] + t * (p2[2] - p1[2])))
                        vi = len(verts) - 1
                        vmap[key] = vi
                    fv.append(vi)
                faces.append(fv)

    if not faces:
        return verts, faces

    V = np.asarray(verts, dtype=np.float64)
    Fc = np.asarray(faces, dtype=np.int32)
    va = V[Fc[:, 0]]; vb = V[Fc[:, 1]]; vc = V[Fc[:, 2]]
    nrm = np.cross(vb - va, vc - va)
    cent = (va + vb + vc) / 3.0
    
    cent_X = cent[:, 0]; cent_Y = cent[:, 1]; cent_Z = cent[:, 2]
    
    if s.bend_angle > 0:
        R = z_len / s.bend_angle
        X_plus_R = cent_X + R
        R_b = np.sqrt(X_plus_R**2 + cent_Z**2)
        X_b = R_b - R
        Y_b = cent_Y
        Z_b = R * np.arctan2(cent_Z, X_plus_R)
    else:
        X_b, Y_b, Z_b = cent_X, cent_Y, cent_Z
        R = 0.0

    if s.twist_angle != 0:
        theta = s.twist_angle * (Z_b / z_len)
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        X_f = X_b * cos_t - Y_b * sin_t
        Y_f = X_b * sin_t + Y_b * cos_t
        Z_f = Z_b
    else:
        X_f, Y_f, Z_f = X_b, Y_b, Z_b

    gx, gy, gz = eval_grad(X_f, Y_f, Z_f, s.mode, s.wings, s.amplitude, s.z_phase)

    if s.twist_angle != 0:
        gx_b = gx * cos_t + gy * sin_t
        gy_b = -gx * sin_t + gy * cos_t
        gz_b = gz
    else:
        gx_b, gy_b, gz_b = gx, gy, gz

    if s.bend_angle > 0:
        phi = Z_b / R
        cos_p = np.cos(phi)
        sin_p = np.sin(phi)
        gx_grid = gx_b * cos_p + gz_b * sin_p
        gy_grid = gy_b
        gz_grid = -gx_b * sin_p + gz_b * cos_p
    else:
        gx_grid, gy_grid, gz_grid = gx_b, gy_b, gz_b

    dot = nrm[:, 0] * gx_grid + nrm[:, 1] * gy_grid + nrm[:, 2] * gz_grid
    flip = dot < 0
    if flip.any():
        Fc2 = Fc.copy()
        Fc2[flip, 1] = Fc[flip, 2]
        Fc2[flip, 2] = Fc[flip, 1]
        Fc = Fc2

    return V.tolist(), Fc.tolist()

# ----------------------------------------------------------------------------
# Generate mesh data (vertices and faces)
# ----------------------------------------------------------------------------
def generate_mesh_data(s):
    res = max(8, s.resolution)
    z_len = s.segments * 2.0 * pi
    
    if s.bend_angle > 0:
        R = z_len / s.bend_angle
        x_min = -2 * R - s.size_xy
        x_max = s.size_xy
    else:
        x_min = -s.size_xy
        x_max = s.size_xy
        
    y_min = -s.size_xy * 1.5
    y_max = s.size_xy * 1.5
    
    dx = 2.0 * s.size_xy / max(1, res - 1)
    
    nx = max(8, int(round((x_max - x_min) / dx)) + 1)
    ny = max(8, int(round((y_max - y_min) / dx)) + 1)
    nz = max(4, int(round(z_len / dx)) + 1)
    
    total = nx * ny * nz
    if total > 12_000_000:
        return None, None, ("Voxel count %d too high. Lower Resolution or Segments." % total)

    xs = np.linspace(x_min, x_max, nx)
    ys = np.linspace(y_min, y_max, ny)
    zs = np.linspace(-z_len * 0.5, z_len * 0.5, nz)

    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    
    if s.bend_angle > 0:
        X_plus_R = X + R
        R_b = np.sqrt(X_plus_R**2 + Z**2)
        X_b = R_b - R
        Y_b = Y
        Z_b = R * np.arctan2(Z, X_plus_R)
    else:
        X_b, Y_b, Z_b = X, Y, Z

    if s.twist_angle != 0:
        theta = s.twist_angle * (Z_b / z_len)
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        X_f = X_b * cos_t - Y_b * sin_t
        Y_f = X_b * sin_t + Y_b * cos_t
        Z_f = Z_b
    else:
        X_f, Y_f, Z_f = X_b, Y_b, Z_b

    F = eval_field(X_f, Y_f, Z_f, s.mode, s.wings, s.amplitude, s.z_phase)
    
    verts, faces = extract_isosurface(xs, ys, zs, F, s)

    if not faces:
        return None, None, "Empty surface (try larger XY Size or Amplitude)."
    
    return verts, faces, "OK"

# ----------------------------------------------------------------------------
# Build the mesh object from the current scene settings
# ----------------------------------------------------------------------------
def build_scherk(context, s):
    t0 = time.time()
    
    verts, faces, msg = generate_mesh_data(s)
    if verts is None:
        return None, msg

    name = "SaddleTower_%s_%dw_%ds" % (s.mode, s.wings, s.segments)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()

    if s.use_smooth:
        for p in me.polygons:
            p.use_smooth = True

    obj = bpy.data.objects.new(name, me)
    coll = context.view_layer.active_layer_collection.collection
    coll.objects.link(obj)

    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    
    s.last_object_name = obj.name

    dt = time.time() - t0
    return obj, "Built %s: %d verts / %d faces in %.1fs" % (
        name, len(verts), len(faces), dt)

# ----------------------------------------------------------------------------
# Live update handler
# ----------------------------------------------------------------------------
def live_update_handler(self, context):
    s = context.scene.scherk
    if not s.live_update or s.is_updating:
        return

    s.is_updating = True
    try:
        obj_name = s.last_object_name
        obj = bpy.data.objects.get(obj_name)
        
        if obj and obj.type == 'MESH':
            verts, faces, msg = generate_mesh_data(s)
            if verts is not None:
                me = obj.data
                me.clear_geometry()
                me.from_pydata(verts, [], faces)
                me.update()
                
                if s.use_smooth:
                    for p in me.polygons:
                        p.use_smooth = True
        else:
            build_scherk(context, s)
    finally:
        s.is_updating = False

# ----------------------------------------------------------------------------
# Settings property group
# ----------------------------------------------------------------------------
def _wings_update(self, context):
    if self.mode == 'EXACT' and self.wings != 4:
        self.mode = 'GENERAL'
    live_update_handler(self, context)

def _mode_update(self, context):
    if self.mode == 'EXACT' and self.wings != 4:
        self.wings = 4
    live_update_handler(self, context)

class ScherkSettings(PropertyGroup):
    mode: EnumProperty(
        name="Formula",
        items=[('EXACT', "Scherk II (exact, 4 wings)",
                "sinh(x)sinh(y) - sin(z) = 0 (true minimal surface)"),
               ('GENERAL', "Saddle Tower N-wing",
                "Im((x+iy)^n) - sin(z) = 0 (n = wings/2, arbitrary branches)")],
        default='EXACT', update=_mode_update)
    wings: IntProperty(name="Branches / Wings",
                       description="Number of horizontal wings (even, >=4).",
                       default=4, min=4, max=24, step=2, update=_wings_update)
    segments: IntProperty(name="Vertical Segments",
                          description="Number of stacked periods in z.",
                          default=2, min=1, max=64, update=live_update_handler)
    resolution: IntProperty(name="Resolution",
                            description="Samples along X and Y.",
                            default=64, min=8, max=300, update=live_update_handler)
    amplitude: FloatProperty(name="Amplitude (hole/branch size)",
                             description="Scales the spatial term.",
                             default=1.0, min=0.01, max=50.0, update=live_update_handler)
    size_xy: FloatProperty(name="XY Size",
                           description="Half-extent of the X/Y bounding box.",
                           default=4.0, min=0.5, max=50.0, update=live_update_handler)
    z_phase: FloatProperty(name="Z Phase",
                           description="Phase offset of sin(z).",
                           default=0.0, min=-pi, max=pi, subtype='ANGLE', update=live_update_handler)
    use_smooth: BoolProperty(name="Shade Smooth", default=True, update=live_update_handler)
    
    bend_angle: FloatProperty(
        name="Bend Angle",
        description="Bend the tower into a torus-like shape (0 to 360 degrees)",
        default=0.0, min=0.0, max=2*pi, subtype='ANGLE', update=live_update_handler
    )
    twist_angle: FloatProperty(
        name="Twist Angle",
        description="Twist the tower around its main axis",
        default=0.0, min=-4*pi, max=4*pi, subtype='ANGLE', update=live_update_handler
    )
    
    # Live update properties
    live_update: BoolProperty(
        name="Live Update",
        description="Automatically regenerate mesh when changing parameters",
        default=False
    )
    last_object_name: StringProperty()
    is_updating: BoolProperty(default=False)

# ----------------------------------------------------------------------------
# Operator
# ----------------------------------------------------------------------------
class MESH_OT_generate_scherk(Operator):
    bl_idname = "mesh.generate_scherk_saddle_tower"
    bl_label = "Generate Saddle Tower (Scherk II)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.scherk
        obj, msg = build_scherk(context, s)
        if obj is None:
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}
        self.report({'INFO'}, msg)
        return {'FINISHED'}

# ----------------------------------------------------------------------------
# UI panel (N-panel)
# ----------------------------------------------------------------------------
class VIEW3D_PT_scherk(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scherk"
    bl_label = "Saddle Tower (Scherk II)"

    def draw(self, context):
        layout = self.layout
        s = context.scene.scherk
        layout.use_property_split = True
        
        layout.prop(s, "mode")
        row = layout.row()
        row.prop(s, "wings")
        row.enabled = (s.mode == 'GENERAL')
        layout.prop(s, "segments")
        layout.prop(s, "amplitude")
        layout.prop(s, "size_xy")
        layout.prop(s, "z_phase")
        layout.prop(s, "resolution")
        layout.prop(s, "use_smooth")
        
        layout.separator()
        layout.label(text="Deformations:", icon='MOD_SIMPLEDEFORM')
        layout.prop(s, "bend_angle")
        layout.prop(s, "twist_angle")
        
        layout.separator()
        layout.prop(s, "live_update", icon='HIDE_OFF' if s.live_update else 'HIDE_ON')

        # live voxel estimate
        z_len = s.segments * 2.0 * pi
        if s.bend_angle > 0:
            R = z_len / s.bend_angle
            x_width = 2 * R + 2 * s.size_xy
        else:
            x_width = 2 * s.size_xy

        y_width = 3 * s.size_xy

        dx = 2.0 * s.size_xy / max(1, s.resolution - 1)
        nx = max(8, int(round(x_width / dx)) + 1)
        ny = max(8, int(round(y_width / dx)) + 1)
        nz = max(4, int(round(z_len / dx)) + 1)
        tot = nx * ny * nz

        box = layout.box()
        box.alert = (tot > 12_000_000)
        box.label(text="Voxels ≈ %d (%d×%d×%d)" % (tot, nx, ny, nz))
        
        layout.operator(MESH_OT_generate_scherk.bl_idname, icon='MESH_TORUS')
        layout.label(text="Tip: add Solidify for thin walls.", icon='INFO')

# ----------------------------------------------------------------------------
# Menu entry
# ----------------------------------------------------------------------------
def _menu_draw(self, context):
    self.layout.operator(MESH_OT_generate_scherk.bl_idname,
                         text="Saddle Tower (Scherk II)", icon='MESH_TORUS')

classes = (ScherkSettings, MESH_OT_generate_scherk, VIEW3D_PT_scherk)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.scherk = PointerProperty(type=ScherkSettings)
    bpy.types.VIEW3D_MT_add.append(_menu_draw)

def unregister():
    bpy.types.VIEW3D_MT_add.remove(_menu_draw)
    del bpy.types.Scene.scherk
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()