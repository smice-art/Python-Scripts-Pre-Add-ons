bl_info = {
    "name": "Scherk Saddle Tower (2nd Scherk Surface)",
    "author": "Shavi",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Scherk  |  Add menu",
    "description": (
        "Generate the 2nd Scherk surface sinh(a x) sinh(b y) - c sin(n z + phi) = 0 "
        "and its n-wing Saddle-Tower generalisation, with adjustable branches/holes."
    ),
    "category": "Add Mesh",
}

import bpy
import bmesh
import math
import time
import numpy as np
from bpy.props import (IntProperty, FloatProperty, BoolProperty,
                       EnumProperty, PointerProperty)
from bpy.types import Operator, Panel, PropertyGroup
from math import pi

# ----------------------------------------------------------------------------
# Marching-tetrahedra table (16 cases).  Tet edge order:
#   e0=(0,1) e1=(0,2) e2=(0,3) e3=(1,2) e4=(1,3) e5=(2,3)
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
# Implicit field  F = amplitude * H(x,y) - sin(n_freq * z + phase)
#   EXACT  : H = sinh(a x) sinh(b y)                  (true minimal surface, 4 wings)
#   GENERAL: H = Im((a x + i b y)^m), m = wings/2      (2m-wing saddle tower)
# a, b independently scale the X/Y spatial frequency in both modes.
# n_freq scales the Z periodicity (bigger n_freq = more holes per Segment).
# ----------------------------------------------------------------------------
def eval_field(X, Y, Z, mode, wings, amplitude, a, b, n_freq, phase):
    if mode == 'EXACT':
        H = np.sinh(a * X) * np.sinh(b * Y)
    else:
        m = max(1, wings // 2)
        H = ((a * X + 1j * b * Y) ** m).imag
    H = np.clip(H, -1e8, 1e8)              # avoid inf -> NaN in interpolation
    return amplitude * H - np.sin(n_freq * Z + phase)


def eval_grad(cx, cy, cz, mode, wings, amplitude, a, b, n_freq, phase):
    if mode == 'EXACT':
        gx = amplitude * a * np.cosh(a * cx) * np.sinh(b * cy)
        gy = amplitude * b * np.sinh(a * cx) * np.cosh(b * cy)
    else:
        m = max(1, wings // 2)
        Wp = (a * cx + 1j * b * cy) ** (m - 1)
        gx = amplitude * a * m * Wp.imag
        gy = amplitude * b * m * Wp.real
    gz = -n_freq * np.cos(n_freq * cz + phase)
    return gx, gy, gz


# ----------------------------------------------------------------------------
# Isosurface extraction (marching tetrahedra) at level 0
# ----------------------------------------------------------------------------
def extract_isosurface(xs, ys, zs, F, mode, wings, amplitude, a, b, n_freq, phase):
    nx, ny, nz = F.shape

    # 8 corners of every cell, shape (nx-1, ny-1, nz-1)
    c = [
        F[:-1, :-1, :-1], F[1:, :-1, :-1], F[:-1, 1:, :-1], F[1:, 1:, :-1],
        F[:-1, :-1, 1:],  F[1:, :-1, 1:],  F[:-1, 1:, 1:],  F[1:, 1:, 1:],
    ]
    stack = np.stack(c, axis=0)
    active = (stack.min(axis=0) <= 0.0) & (stack.max(axis=0) >= 0.0)
    ii, jj, kk = np.nonzero(active)

    verts = []
    faces = []
    vmap = {}                                 # shared edge-crossing vertices
    nxy = nx * ny

    DI_l = DI.tolist(); DJ_l = DJ.tolist(); DK_l = DK.tolist()

    for idx in range(ii.size):
        i = int(ii[idx]); j = int(jj[idx]); k = int(kk[idx])

        VL = (c[0][i, j, k], c[1][i, j, k], c[2][i, j, k], c[3][i, j, k],
              c[4][i, j, k], c[5][i, j, k], c[6][i, j, k], c[7][i, j, k])
        PL = tuple(
            (xs[i + DI_l[l]], ys[j + DJ_l[l]], zs[k + DK_l[l]]) for l in range(8)
        )
        GI = tuple(
            (i + DI_l[l]) + (j + DJ_l[l]) * nx + (k + DK_l[l]) * nxy for l in range(8)
        )

        for (av, bv, cc, dv) in TETS:
            va, vb, vc, vd = VL[av], VL[bv], VL[cc], VL[dv]
            mask = (1 if va > 0 else 0) | (2 if vb > 0 else 0) | \
                   (4 if vc > 0 else 0) | (8 if vd > 0 else 0)
            tris = TET_TABLE[mask]
            if not tris:
                continue
            te = ((av, bv), (av, cc), (av, dv), (bv, cc), (bv, dv), (cc, dv))
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

    # ---- orient triangles consistently using the analytic gradient ----
    V = np.asarray(verts, dtype=np.float64)
    Fc = np.asarray(faces, dtype=np.int32)
    va = V[Fc[:, 0]]; vb = V[Fc[:, 1]]; vc = V[Fc[:, 2]]
    nrm = np.cross(vb - va, vc - va)
    cent = (va + vb + vc) / 3.0
    gx, gy, gz = eval_grad(cent[:, 0], cent[:, 1], cent[:, 2],
                           mode, wings, amplitude, a, b, n_freq, phase)
    dot = nrm[:, 0] * gx + nrm[:, 1] * gy + nrm[:, 2] * gz
    flip = dot < 0
    if flip.any():
        Fc2 = Fc.copy()
        Fc2[flip, 1] = Fc[flip, 2]
        Fc2[flip, 2] = Fc[flip, 1]
        Fc = Fc2
    return V.tolist(), Fc.tolist()


# ----------------------------------------------------------------------------
# Build the mesh object from the current scene settings
# ----------------------------------------------------------------------------
def build_scherk(context, s):
    t0 = time.time()
    res = max(8, s.resolution)
    z_len = s.segments * 2.0 * pi / max(abs(s.n_freq), 1e-6)
    # tiny epsilon offset avoids exact-zero grid ties along symmetry axes
    xs = np.linspace(-s.size_xy, s.size_xy, res) + 1e-7
    ys = np.linspace(-s.size_xy, s.size_xy, res) + 1e-7
    dx = xs[1] - xs[0]
    nz = max(4, int(round(z_len / dx)) + 1)
    zs = np.linspace(-z_len * 0.5, z_len * 0.5, nz) + 1e-7

    total = res * res * nz
    if total > 12_000_000:
        return None, ("Voxel count %d too high. Lower Resolution or Segments." % total)

    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    F = eval_field(X, Y, Z, s.mode, s.wings, s.amplitude, s.scale_a, s.scale_b, s.n_freq, s.z_phase)

    verts, faces = extract_isosurface(xs, ys, zs, F, s.mode, s.wings, s.amplitude,
                                      s.scale_a, s.scale_b, s.n_freq, s.z_phase)
    if not faces:
        return None, "Empty surface (try larger XY Size or Amplitude)."

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

    dt = time.time() - t0
    return obj, "Built %s: %d verts / %d faces in %.1fs  (grid %dx%dx%d)" % (
        name, len(verts), len(faces), dt, res, res, nz)


# ----------------------------------------------------------------------------
# Settings property group
# ----------------------------------------------------------------------------
def _wings_update(self, context):
    if self.mode == 'EXACT' and self.wings != 4:
        self.mode = 'GENERAL'


def _mode_update(self, context):
    if self.mode == 'EXACT' and self.wings != 4:
        self.wings = 4


class ScherkSettings(PropertyGroup):
    mode: EnumProperty(
        name="Formula",
        items=[('EXACT', "Scherk II (exact, 4 wings)",
                "sinh(a x) sinh(b y) - sin(n z + phase) = 0  (true minimal surface)"),
               ('GENERAL', "Saddle Tower N-wing",
                "Im((a x + i b y)^m) - sin(n z + phase) = 0  (m = wings/2, arbitrary branches)")],
        default='EXACT', update=_mode_update)
    wings: IntProperty(name="Branches / Wings",
                       description="Number of horizontal wings (even, >=4). "
                                   "Forces the N-wing generalised formula.",
                       default=4, min=4, max=24, step=2, update=_wings_update)
    segments: IntProperty(name="Vertical Segments",
                          description="Number of stacked periods in z "
                                      "(each adds a row of holes/windows).",
                          default=2, min=1, max=64)
    resolution: IntProperty(name="Resolution",
                            description="Samples along X and Y (Z is scaled "
                                        "to keep cubic voxels).",
                            default=64, min=8, max=300)
    amplitude: FloatProperty(name="Amplitude c (hole/branch size)",
                             description="Scales the spatial term; larger = "
                                         "thinner wings / bigger holes.",
                             default=1.0, min=0.01, max=50.0)
    scale_a: FloatProperty(name="a (X scale)",
                           description="Independent X-axis scale in sinh(a x) / (a x + i b y).",
                           default=1.0, min=0.05, max=10.0)
    scale_b: FloatProperty(name="b (Y scale)",
                           description="Independent Y-axis scale in sinh(b y) / (a x + i b y).",
                           default=1.0, min=0.05, max=10.0)
    n_freq: FloatProperty(name="n (Z frequency)",
                          description="Frequency of sin(n z + phase); higher packs "
                                      "holes tighter for the same Segments count.",
                          default=1.0, min=0.1, max=10.0)
    size_xy: FloatProperty(name="XY Size",
                           description="Half-extent of the X/Y bounding box.",
                           default=4.0, min=0.5, max=50.0)
    z_phase: FloatProperty(name="Z Phase",
                           description="Phase offset of sin(n z + phase); shifts where "
                                       "holes/saddles sit vertically.",
                           default=0.0, min=-pi, max=pi, subtype='ANGLE')
    use_smooth: BoolProperty(name="Shade Smooth", default=True)


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
        layout.prop(s, "scale_a")
        layout.prop(s, "scale_b")
        layout.prop(s, "n_freq")
        layout.prop(s, "size_xy")
        layout.prop(s, "z_phase")
        layout.prop(s, "resolution")
        layout.prop(s, "use_smooth")

        # live voxel estimate
        dx = 2.0 * s.size_xy / max(1, s.resolution - 1)
        z_len = s.segments * 2 * pi / max(abs(s.n_freq), 1e-6)
        nz = max(4, int(round(z_len / dx)) + 1)
        tot = s.resolution * s.resolution * nz
        box = layout.box()
        box.alert = (tot > 12_000_000)
        box.label(text="Voxels ~ %d  (%d x %d x %d)" % (
            tot, s.resolution, s.resolution, nz))

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
