"""
SPHERE EVERSION toolkit for Blender - N-panel add-on
=====================================================

Two independent generators, selectable in the N-panel (View3D > Sidebar >
"Eversion" tab):

1) BEDNORZ  - a fully animated, explicit, closed-form sphere eversion.
   Math ported from PyVista's verified implementation of:
   Adam Bednorz & Witold Bednorz, Differential Geometry and its Applications
   64 (2019), 59. https://arxiv.org/abs/1711.10466
   This is NOT the same surface as the poster (which shows the Kusner-Morin
   *minimax* eversion), but it is a real, rigorously proven eversion with a
   similar self-intersecting multi-lobed halfway stage.

2) KUSNER / MORIN HALFWAY MODEL (experimental, static) - builds the actual
   Kusner minimal surface via its published Weierstrass-type formula:
   R. Kusner, "Conformal geometry and complete minimal surfaces",
   Bull. AMS 17 (1987), 291-295, as transcribed by the 3D-XplorMath project
   (https://virtualmathmuseum.org/Surface/kusner_ds/kusner_ds.html).
   For p = 4 that source states this surface, inverted in the unit sphere,
   IS the Morin sphere-eversion halfway model shown in your poster - i.e.
   this is the actual halfway snapshot, not an animated approximation of it.
   CAVEAT: the exact domain bounds (u_min/u_max range for the radial
   parameter) used by the original 3DXM renderer were not published in the
   source I could verify, so they are exposed as sliders here for you to
   tune live rather than hard-coded. Expect to need to adjust them (and
   possibly toggle "Both bands") to get a clean, non-exploding patch.
   There is no known closed-form for the *motion* through the eversion
   (the real minimax eversion is computed by a numerical Willmore-energy
   gradient flow in Brakke's Surface Evolver) - this generator only gives
   you the static halfway shape, for comparison against the poster.

INSTALL
-------
Blender Preferences > Add-ons > Install... > select this file > enable
"Sphere Eversion Toolkit". A new "Eversion" tab appears in the 3D
Viewport's N-panel (press N to open it).

You can also just paste this whole file into the Scripting tab and hit
Run Script - it registers itself immediately via the __main__ fallback
at the bottom.
"""

bl_info = {
    "name": "Sphere Eversion Toolkit",
    "author": "Claudio",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Eversion",
    "description": "Generate explicit sphere eversions (Bednorz animated / Kusner-Morin halfway model)",
    "category": "Add Mesh",
}

import bpy
import numpy as np
from bpy.props import (
    IntProperty, FloatProperty, BoolProperty, EnumProperty, PointerProperty,
)
from bpy.types import PropertyGroup, Operator, Panel

BEDNORZ_OBJ_NAME = "SphereEversion_Bednorz"
KUSNER_OBJ_NAME = "KusnerMorinSurface"

# module-level cache: object name -> list of flattened float32 vertex arrays
_FRAME_CACHE = {}


# ----------------------------------------------------------------------
# shared helpers
# ----------------------------------------------------------------------

def _clear_object(name):
    if name in bpy.data.objects:
        old = bpy.data.objects[name]
        old_mesh = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if old_mesh and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)


def _make_grid_faces(res_a, res_b, periodic_b=False):
    faces = []
    for i in range(res_a - 1):
        for j in range(res_b - (0 if periodic_b else 1)):
            j2 = (j + 1) % res_b
            a = i * res_b + j
            b = (i + 1) * res_b + j
            c = (i + 1) * res_b + j2
            d = i * res_b + j2
            faces.append((a, b, c, d))
    return faces


def _smooth_shade(obj):
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for f in obj.data.polygons:
        f.use_smooth = True


# ----------------------------------------------------------------------
# 1) BEDNORZ explicit animated eversion
# ----------------------------------------------------------------------

def _bednorz_build_frames(s):
    n = s.bednorz_n_lobes
    kappa = (n - 1) / (2 * n)
    Q, W, beta = s.bednorz_Q, s.bednorz_W, s.bednorz_beta
    alpha_final, eta_final = s.bednorz_alpha_final, s.bednorz_eta_final
    n_steps = s.bednorz_steps_per_stage

    def sphere_to_cylinder(theta, phi):
        h = W * np.sin(theta) / np.cos(theta) ** n
        return h, phi

    def cylinder_to_wormhole(h, phi, t, p, q):
        x = t * np.cos(phi) + p * np.sin((n - 1) * phi) - h * np.sin(phi)
        y = t * np.sin(phi) + p * np.cos((n - 1) * phi) + h * np.cos(phi)
        z = h * np.sin(n * phi) - t / n * np.cos(n * phi) - q * t * h
        return x, y, z

    def close_wormhole(x0, y0, z0, eta, xi, alpha):
        denom = xi + eta * (x0 ** 2 + y0 ** 2)
        x1 = x0 / (denom ** kappa)
        y1 = y0 / (denom ** kappa)
        z1 = z0 / denom
        gamma = 2 * np.sqrt(alpha * beta)
        if np.isclose(gamma, 0):
            denom2 = x1 ** 2 + y1 ** 2
            return x1 / denom2, y1 / denom2, -z1
        expo = np.exp(gamma * z1)
        num = alpha - beta * (x1 ** 2 + y1 ** 2)
        den = alpha + beta * (x1 ** 2 + y1 ** 2)
        x2 = x1 * expo / den
        y2 = y1 * expo / den
        z2 = num / den * expo / gamma - (alpha - beta) / (alpha + beta) / gamma
        return x2, y2, z2

    def unfold_sphere(theta, phi, t, q, eta, lamda):
        x = (t * (1 - lamda + lamda * np.cos(theta) ** n) * np.cos(phi)
             - lamda * W * np.sin(theta) * np.sin(phi))
        x /= np.cos(theta) ** n
        y = (t * (1 - lamda + lamda * np.cos(theta) ** n) * np.sin(phi)
             + lamda * W * np.sin(theta) * np.cos(phi))
        y /= np.cos(theta) ** n
        z = (lamda * ((W * np.sin(theta) * (np.sin(n * phi) - q * t)) / np.cos(theta) ** n
                       - t / n * np.cos(n * phi))
             - (1 - lamda) * eta ** (1 + kappa) * t * abs(t) ** (2 * kappa)
             * np.sin(theta) / np.cos(theta) ** (2 * n))
        denom = x ** 2 + y ** 2
        x2 = x * eta ** kappa / denom ** (1 - kappa)
        y2 = y * eta ** kappa / denom ** (1 - kappa)
        z2 = -z / eta / denom
        return x2, y2, z2

    theta, phi = np.mgrid[
        -np.pi / 2: np.pi / 2: s.bednorz_res_theta * 1j,
        -np.pi: np.pi: s.bednorz_res_phi * 1j,
    ]

    t = -1 / Q
    q = Q
    p = xi = alpha = 0
    eta = 1
    frames = []

    h, phi2 = sphere_to_cylinder(theta, phi)

    for lamda in np.linspace(0, 1, n_steps, endpoint=False):
        frames.append(unfold_sphere(theta, phi, t, q, eta, lamda))

    x, y, z = cylinder_to_wormhole(h, phi2, t, p, q)
    xis = np.linspace(0, 1, n_steps)
    alphas = np.linspace(0, alpha_final, n_steps)
    etas = np.linspace(1, eta_final, n_steps)
    for xi, alpha, eta in zip(xis, alphas, etas):
        frames.append(close_wormhole(x, y, z, eta, xi, alpha))

    for q in np.linspace(Q, 0, n_steps):
        p = 1 - abs(q * t)
        x, y, z = cylinder_to_wormhole(h, phi2, t, p, q)
        frames.append(close_wormhole(x, y, z, eta, xi, alpha))

    for t in np.linspace(-1 / Q, 1 / Q, n_steps):
        p = 1 - abs(q * t)
        x, y, z = cylinder_to_wormhole(h, phi2, t, p, q)
        frames.append(close_wormhole(x, y, z, eta, xi, alpha))

    for q in np.linspace(0, Q, n_steps + 1)[1:]:
        p = 1 - abs(q * t)
        x, y, z = cylinder_to_wormhole(h, phi2, t, p, q)
        frames.append(close_wormhole(x, y, z, eta, xi, alpha))

    x, y, z = cylinder_to_wormhole(h, phi2, t, p, q)
    xis = np.linspace(1, 0, n_steps + 1)[1:]
    alphas = np.linspace(alpha_final, 0, n_steps + 1)[1:]
    for xi, alpha in zip(xis, alphas):
        frames.append(close_wormhole(x, y, z, eta, xi, alpha))

    for lamda in np.linspace(1, 0, n_steps + 1)[1:]:
        frames.append(unfold_sphere(theta, phi, t, q, eta, lamda))

    return frames


def _flatten_frame(xyz, scale):
    x, y, z = xyz
    pts = np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1) * scale
    pts = np.nan_to_num(pts, nan=0.0, posinf=0.0, neginf=0.0)
    return pts.astype(np.float32).flatten()


def _bednorz_frame_change_handler(scene, depsgraph=None):
    obj = bpy.data.objects.get(BEDNORZ_OBJ_NAME)
    frames = _FRAME_CACHE.get(BEDNORZ_OBJ_NAME)
    if obj is None or not frames:
        return
    idx = (scene.frame_current - scene.frame_start) % len(frames)
    obj.data.vertices.foreach_set("co", frames[idx])
    obj.data.update()


class EVERSION_OT_build_bednorz(Operator):
    bl_idname = "eversion.build_bednorz"
    bl_label = "Build Bednorz Eversion (Animated)"
    bl_description = "Generate the animated explicit sphere eversion and bind it to the timeline"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.eversion_settings
        try:
            frames_xyz = _bednorz_build_frames(s)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to build frames: {e}")
            return {'CANCELLED'}

        flat_frames = [_flatten_frame(f, s.bednorz_scale) for f in frames_xyz]

        _clear_object(BEDNORZ_OBJ_NAME)
        mesh = bpy.data.meshes.new(BEDNORZ_OBJ_NAME)
        obj = bpy.data.objects.new(BEDNORZ_OBJ_NAME, mesh)
        context.collection.objects.link(obj)

        verts0 = flat_frames[0].reshape(-1, 3).tolist()
        faces = _make_grid_faces(s.bednorz_res_theta, s.bednorz_res_phi, periodic_b=False)
        mesh.from_pydata(verts0, [], faces)
        mesh.update()

        _FRAME_CACHE[BEDNORZ_OBJ_NAME] = flat_frames

        scene = context.scene
        scene.frame_start = 1
        scene.frame_end = len(flat_frames)
        scene.frame_current = 1

        for h in list(bpy.app.handlers.frame_change_pre):
            if getattr(h, "__name__", "") == "_bednorz_frame_change_handler":
                bpy.app.handlers.frame_change_pre.remove(h)
        bpy.app.handlers.frame_change_pre.append(_bednorz_frame_change_handler)
        _bednorz_frame_change_handler(scene)

        _smooth_shade(obj)
        self.report({'INFO'}, f"Built {len(flat_frames)} frames. Scrub the timeline to play.")
        return {'FINISHED'}


# ----------------------------------------------------------------------
# 2) KUSNER minimal surface / Morin halfway model (experimental, static)
# ----------------------------------------------------------------------

def _kusner_build_mesh(s):
    p = s.kusner_p

    def P_of_z(z):
        a = 1.0 / (z ** p - z ** (-p) + (2.0 / (p - 1)) * np.sqrt(2 * p - 1))
        v1 = 1j * (z ** (p - 1) + z ** (1 - p))
        v2 = z ** (p - 1) + z ** (1 - p)
        v3 = 1j * (p - 1) / p * (z ** p + z ** (-p))
        x = np.real(a * v1)
        y = np.real(a * v2)
        zc = np.real(a * v3) + s.kusner_offset_aa
        return x, y, zc

    bands = [(s.kusner_u_min, s.kusner_u_max)]
    if s.kusner_both_bands:
        bands.append((-s.kusner_u_max, -s.kusner_u_min))

    all_verts = []
    all_faces = []
    ru, rv = s.kusner_u_steps, s.kusner_v_steps

    for (umin, umax) in bands:
        uu, vv = np.mgrid[umin:umax:ru * 1j, 0:2 * np.pi:rv * 1j]
        z = uu * np.cos(vv) + 1j * uu * np.sin(vv)
        x, y, zc = P_of_z(z)

        if s.kusner_apply_inversion:
            r2 = x ** 2 + y ** 2 + zc ** 2
            r2 = np.where(r2 < 1e-9, 1e-9, r2)
            x, y, zc = x / r2, y / r2, zc / r2

        x *= s.kusner_scale
        y *= s.kusner_scale
        zc *= s.kusner_scale

        base = len(all_verts)
        pts = np.stack([x.ravel(), y.ravel(), zc.ravel()], axis=1)
        pts = np.nan_to_num(pts, nan=0.0, posinf=0.0, neginf=0.0)
        all_verts.extend(pts.tolist())

        band_faces = _make_grid_faces(ru, rv, periodic_b=True)
        all_faces.extend([(a + base, b + base, c + base, d + base) for a, b, c, d in band_faces])

    return all_verts, all_faces


class EVERSION_OT_build_kusner(Operator):
    bl_idname = "eversion.build_kusner"
    bl_label = "Build Kusner / Morin Surface (Experimental)"
    bl_description = ("Generate the static Kusner minimal surface (p=4 + inversion = Morin "
                       "halfway model). Domain bounds are approximate - tune the sliders")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.eversion_settings
        try:
            verts, faces = _kusner_build_mesh(s)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to build surface: {e}")
            return {'CANCELLED'}

        _clear_object(KUSNER_OBJ_NAME)
        mesh = bpy.data.meshes.new(KUSNER_OBJ_NAME)
        obj = bpy.data.objects.new(KUSNER_OBJ_NAME, mesh)
        context.collection.objects.link(obj)
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        _smooth_shade(obj)
        self.report({'INFO'}, f"Built Kusner surface (p={s.kusner_p}, "
                               f"{'inverted / Morin model' if s.kusner_apply_inversion else 'raw minimal surface'}).")
        return {'FINISHED'}


# ----------------------------------------------------------------------
# settings, panel, registration
# ----------------------------------------------------------------------

def _auto_rebuild(self, context):
    """update= callback: re-runs the appropriate build operator whenever a
    watched property changes, but only if Auto Update is enabled."""
    s = context.scene.eversion_settings
    if not s.auto_update:
        return
    try:
        if s.mode == 'BEDNORZ':
            bpy.ops.eversion.build_bednorz()
        else:
            bpy.ops.eversion.build_kusner()
    except RuntimeError:
        # e.g. no suitable context while dragging - safe to ignore, next
        # change (or a manual button press) will retry
        pass


class EversionSettings(PropertyGroup):
    auto_update: BoolProperty(
        name="Auto Update",
        default=False,
        description=("Rebuild automatically whenever a parameter changes. "
                     "Handy for tuning, but can lag with high resolution or "
                     "many animation steps"),
    )

    mode: EnumProperty(
        name="Generator",
        items=[
            ('BEDNORZ', "Bednorz (animated)", "Explicit closed-form eversion, fully animated"),
            ('KUSNER', "Kusner / Morin (experimental)", "Static Kusner minimal surface / Morin halfway model"),
        ],
        default='BEDNORZ',
        update=_auto_rebuild,
    )

    # -- Bednorz params --
    bednorz_res_theta: IntProperty(name="Res Theta", default=60, min=8, max=400, update=_auto_rebuild)
    bednorz_res_phi: IntProperty(name="Res Phi", default=120, min=8, max=800, update=_auto_rebuild)
    bednorz_steps_per_stage: IntProperty(name="Steps / Stage", default=12, min=2, max=200, update=_auto_rebuild)
    bednorz_n_lobes: IntProperty(name="Lobes (N)", default=3, min=2, max=8, update=_auto_rebuild)
    bednorz_Q: FloatProperty(name="Q", default=2.0 / 3.0, min=0.01, max=0.99, update=_auto_rebuild)
    bednorz_W: FloatProperty(name="W", default=2.0, min=0.01, max=20.0, update=_auto_rebuild)
    bednorz_beta: FloatProperty(name="Beta", default=1.0, min=0.01, max=20.0, update=_auto_rebuild)
    bednorz_alpha_final: FloatProperty(name="Alpha Final", default=1.0, min=0.01, max=20.0, update=_auto_rebuild)
    bednorz_eta_final: FloatProperty(name="Eta Final", default=2.0, min=1.01, max=20.0, update=_auto_rebuild)
    bednorz_scale: FloatProperty(name="Scale", default=0.3, min=0.001, max=100.0, update=_auto_rebuild)

    # -- Kusner params --
    kusner_p: IntProperty(name="p (symmetry)", default=4, min=2, max=12,
                           description="p=4 -> Morin halfway model, p=3 -> inverted Boy surface",
                           update=_auto_rebuild)
    kusner_u_min: FloatProperty(name="U Min", default=0.3, min=0.001, max=10.0, update=_auto_rebuild)
    kusner_u_max: FloatProperty(name="U Max", default=2.0, min=0.01, max=20.0, update=_auto_rebuild)
    kusner_u_steps: IntProperty(name="U Steps", default=40, min=4, max=400, update=_auto_rebuild)
    kusner_v_steps: IntProperty(name="V Steps", default=120, min=8, max=800, update=_auto_rebuild)
    kusner_both_bands: BoolProperty(name="Both Bands (u>0 and u<0)", default=True, update=_auto_rebuild)
    kusner_apply_inversion: BoolProperty(
        name="Apply Inversion (Morin model)", default=True,
        description="Off = raw Kusner minimal surface. On = inverted in unit sphere = Morin halfway model",
        update=_auto_rebuild)
    kusner_offset_aa: FloatProperty(name="Z Offset", default=0.0, min=-10.0, max=10.0, update=_auto_rebuild)
    kusner_scale: FloatProperty(name="Scale", default=1.0, min=0.001, max=100.0, update=_auto_rebuild)


class EVERSION_PT_panel(Panel):
    bl_label = "Sphere Eversion"
    bl_idname = "EVERSION_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Eversion"

    def draw(self, context):
        layout = self.layout
        s = context.scene.eversion_settings
        layout.prop(s, "auto_update", icon='FILE_REFRESH')
        layout.prop(s, "mode")

        if s.mode == 'BEDNORZ':
            box = layout.box()
            box.label(text="Bednorz explicit eversion (animated)")
            col = box.column(align=True)
            col.prop(s, "bednorz_res_theta")
            col.prop(s, "bednorz_res_phi")
            col.prop(s, "bednorz_steps_per_stage")
            col.prop(s, "bednorz_n_lobes")
            col.prop(s, "bednorz_Q")
            col.prop(s, "bednorz_W")
            col.prop(s, "bednorz_beta")
            col.prop(s, "bednorz_alpha_final")
            col.prop(s, "bednorz_eta_final")
            col.prop(s, "bednorz_scale")
            box.operator("eversion.build_bednorz", icon='MOD_SIMPLEDEFORM')
        else:
            box = layout.box()
            box.label(text="Kusner surface / Morin halfway model", icon='ERROR')
            box.label(text="Static shape - domain bounds approximate,")
            box.label(text="tune sliders below if it looks broken.")
            col = box.column(align=True)
            col.prop(s, "kusner_p")
            col.prop(s, "kusner_u_min")
            col.prop(s, "kusner_u_max")
            col.prop(s, "kusner_u_steps")
            col.prop(s, "kusner_v_steps")
            col.prop(s, "kusner_both_bands")
            col.prop(s, "kusner_apply_inversion")
            col.prop(s, "kusner_offset_aa")
            col.prop(s, "kusner_scale")
            box.operator("eversion.build_kusner", icon='MOD_SIMPLEDEFORM')


classes = (
    EversionSettings,
    EVERSION_OT_build_bednorz,
    EVERSION_OT_build_kusner,
    EVERSION_PT_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.eversion_settings = PointerProperty(type=EversionSettings)


def unregister():
    for h in list(bpy.app.handlers.frame_change_pre):
        if getattr(h, "__name__", "") == "_bednorz_frame_change_handler":
            bpy.app.handlers.frame_change_pre.remove(h)
    del bpy.types.Scene.eversion_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
