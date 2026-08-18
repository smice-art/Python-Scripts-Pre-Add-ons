bl_info = {
    "name": "Sphere Eversion (Bednorz-Bednorz)",
    "author": "Claudio",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > N-Panel > Eversion",
    "description": (
        "Generates an exact analytic sphere eversion surface following "
        "Bednorz & Bednorz, 'Analytic sphere eversion using ruled surfaces' "
        "(Diff. Geom. Appl. 64, 2019). Progress t=0 is the round sphere, "
        "t=1 is the sphere turned inside out (the antipodal map), t=0.5 "
        "passes through the symmetric halfway (twist) model."
    ),
    "category": "Add Mesh",
}

import bpy
import bmesh
import math
from bpy.app.handlers import persistent

# ---------------------------------------------------------------------------
# CORE MATHEMATICS
#
# Source: Adam Bednorz & Witold Bednorz, "Analytic sphere eversion using
# ruled surfaces", Differential Geometry and its Applications 64 (2019).
# arXiv:1711.10466
#
# The eversion is driven by a single master parameter PROGRESS in [0, 1]
# and is built out of 7 analytic phases (Table 1 of the paper, read
# bottom-to-top then top-to-bottom):
#
#   A  sphere            -> inverted wormhole   (lambda: 0 -> 1)
#   B  inverted wormhole -> unfolded wormhole    (xi: 0->1, alpha: eps->1)
#   C  unfolded wormhole -> closed wormhole      (q: Q -> 0)          "pucker"
#   D  closed wormhole,  t: -1/Q -> +1/Q         (the "twist")
#   E  closed wormhole   -> unfolded wormhole     (q: 0 -> Q)
#   F  unfolded wormhole -> inverted wormhole     (xi: 1->0, alpha: 1->eps)
#   G  inverted wormhole -> sphere (inside-out)   (lambda: 1 -> 0)
#
# Phases A and G use the closed-form eqs. (12)+(15)+(10) of the paper,
# which are the removable-singularity form valid exactly at alpha=xi=0.
# Phases B-F use the general pipeline: eq. (4) [with h = omega*sin(theta)
# / cos(theta)^n], then the two inversions eq. (7) and eq. (8). alpha is
# clamped a small epsilon away from 0 there since eq. (8) is singular at
# alpha=0 (gamma = 2*sqrt(alpha*beta) -> 0).
#
# theta in (-pi/2, pi/2) is clamped away from the exact poles (pole_epsilon)
# since cos(theta)**n sits in a denominator; the poles are closed with a
# small fan cap after meshing.
# ---------------------------------------------------------------------------


def _general_pipeline(theta, phi, n, t, q, xi, eta, alpha, beta, omega=2.0):
    """eqs. (4), (7), (8). Requires xi>0 or alpha>0."""
    kappa = (n - 1) / (2.0 * n)
    gamma = 2.0 * math.sqrt(max(alpha * beta, 0.0))

    ct = math.cos(theta)
    h = omega * math.sin(theta) / (ct ** n)
    p = max(1.0 - abs(q * t), 0.0)

    x = t * math.cos(phi) + p * math.sin((n - 1) * phi) - h * math.sin(phi)
    y = t * math.sin(phi) + p * math.cos((n - 1) * phi) + h * math.cos(phi)
    z = h * math.sin(n * phi) - (t / n) * math.cos(n * phi) - q * t * h

    d1 = max(xi + eta * (x * x + y * y), 1e-12)
    xp = x * d1 ** (-kappa)
    yp = y * d1 ** (-kappa)
    zp = z / d1

    d2 = max(alpha + beta * (xp * xp + yp * yp), 1e-12)
    gz = max(-700.0, min(700.0, gamma * zp))
    egz = math.exp(gz)
    xpp = xp * egz / d2
    ypp = yp * egz / d2
    if gamma > 1e-9:
        zpp = (alpha - beta * (xp * xp + yp * yp)) / d2 * egz / gamma \
              - (1.0 / gamma) * (alpha - beta) / (alpha + beta)
    else:
        zpp = zp
    return xpp, ypp, zpp


def _lambda_blend(theta, phi, n, t, q, lam, omega=2.0, eta=1.0):
    """eqs. (12) + (15) + (10): sphere <-> pure (p=0) wormhole, exact at alpha=xi=0."""
    kappa = (n - 1) / (2.0 * n)
    ct = math.cos(theta)
    st = math.sin(theta)
    cn = ct ** n

    x = (t * (1 - lam + lam * cn) * math.cos(phi) - lam * omega * st * math.sin(phi)) / cn
    y = (t * (1 - lam + lam * cn) * math.sin(phi) + lam * omega * st * math.cos(phi)) / cn
    z = lam * (omega * st * (math.sin(n * phi) - q * t) / cn - (t / n) * math.cos(n * phi)) \
        - (1 - lam) * eta ** (1 + kappa) * t * (abs(t) ** (2 * kappa)) * st / (ct ** (2 * n))

    r2 = max(x * x + y * y, 1e-12)
    xpp = eta ** kappa * x / (r2 ** (1 - kappa))
    ypp = eta ** kappa * y / (r2 ** (1 - kappa))
    zpp = -(z / eta) / r2
    return xpp, ypp, zpp


def eversion_point(theta, phi, progress, n=2, Q=0.66, alpha_eps=0.01):
    """Full 7-phase eversion. progress in [0,1]. n>=2 (number of arms/lobes)."""
    t1 = 1.0 / Q
    seg = 1.0 / 7.0
    s = max(0.0, min(1.0, progress))

    def local(k):
        lo = k * seg
        return max(0.0, min(1.0, (s - lo) / seg))

    if s <= seg:
        lam = local(0)
        return _lambda_blend(theta, phi, n, t=-t1, q=Q, lam=lam)
    elif s <= 2 * seg:
        u = local(1)
        xi = u
        alpha = alpha_eps + u * (1.0 - alpha_eps)
        return _general_pipeline(theta, phi, n, t=-t1, q=Q, xi=xi, eta=1.0, alpha=alpha, beta=1.0)
    elif s <= 3 * seg:
        u = local(2)
        q = Q * (1 - u)
        return _general_pipeline(theta, phi, n, t=-t1, q=q, xi=1.0, eta=1.0, alpha=1.0, beta=1.0)
    elif s <= 4 * seg:
        u = local(3)
        t = -t1 + u * (2 * t1)
        return _general_pipeline(theta, phi, n, t=t, q=0.0, xi=1.0, eta=1.0, alpha=1.0, beta=1.0)
    elif s <= 5 * seg:
        u = local(4)
        q = Q * u
        return _general_pipeline(theta, phi, n, t=t1, q=q, xi=1.0, eta=1.0, alpha=1.0, beta=1.0)
    elif s <= 6 * seg:
        u = local(5)
        xi = 1 - u
        alpha = 1.0 + u * (alpha_eps - 1.0)
        return _general_pipeline(theta, phi, n, t=t1, q=Q, xi=xi, eta=1.0, alpha=alpha, beta=1.0)
    else:
        u = local(6)
        lam = 1 - u
        return _lambda_blend(theta, phi, n, t=t1, q=Q, lam=lam)


def latitude_color(u):
    """u in [0,1] (normalized theta) -> blue -> green -> yellow gradient."""
    blue = (0.05, 0.30, 0.75)
    green = (0.20, 0.70, 0.35)
    yellow = (0.95, 0.85, 0.15)
    if u < 0.5:
        f = u / 0.5
        c = tuple(blue[i] + (green[i] - blue[i]) * f for i in range(3))
    else:
        f = (u - 0.5) / 0.5
        c = tuple(green[i] + (yellow[i] - green[i]) * f for i in range(3))
    return c + (1.0,)


# ---------------------------------------------------------------------------
# MESH GENERATION
# ---------------------------------------------------------------------------

OBJECT_NAME = "SphereEversion"
MATERIAL_NAME = "SphereEversion_Material"


def build_mesh(mesh, props):
    n = props.n_arms
    Q = props.Q
    T = props.progress
    alpha_eps = props.alpha_epsilon
    pole_eps = props.pole_epsilon
    res_t = props.resolution_theta
    res_p = props.resolution_phi
    scale = props.radius_scale

    theta_max = math.pi / 2 - pole_eps
    thetas = [-theta_max + i * (2 * theta_max) / res_t for i in range(res_t + 1)]
    phis = [-math.pi + j * (2 * math.pi) / res_p for j in range(res_p)]

    bm = bmesh.new()
    color_layer = bm.verts.layers.float_color.new("Latitude")

    min_r = float("inf")
    max_r = 0.0

    grid = [[None] * res_p for _ in range(res_t + 1)]
    for i, th in enumerate(thetas):
        u = (th + theta_max) / (2 * theta_max)  # 0..1 for coloring
        col = latitude_color(u)
        for j, ph in enumerate(phis):
            x, y, z = eversion_point(th, ph, T, n=n, Q=Q, alpha_eps=alpha_eps)
            x, y, z = x * scale, y * scale, z * scale
            r = math.sqrt(x * x + y * y + z * z)
            if r < min_r:
                min_r = r
            if r > max_r:
                max_r = r
            v = bm.verts.new((x, y, z))
            v[color_layer] = col
            grid[i][j] = v

    bm.verts.ensure_lookup_table()

    for i in range(res_t):
        for j in range(res_p):
            j2 = (j + 1) % res_p
            v00 = grid[i][j]
            v01 = grid[i][j2]
            v10 = grid[i + 1][j]
            v11 = grid[i + 1][j2]
            try:
                bm.faces.new((v00, v10, v11, v01))
            except ValueError:
                pass  # degenerate face, skip

    # Fan-cap the two small polar openings so the surface reads as closed.
    for ring, reverse in ((grid[0], True), (grid[-1], False)):
        cx = sum(v.co.x for v in ring) / len(ring)
        cy = sum(v.co.y for v in ring) / len(ring)
        cz = sum(v.co.z for v in ring) / len(ring)
        pole_v = bm.verts.new((cx, cy, cz))
        pole_v[color_layer] = ring[0][color_layer]
        for j in range(res_p):
            j2 = (j + 1) % res_p
            a, b = ring[j], ring[j2]
            tri = (pole_v, b, a) if reverse else (pole_v, a, b)
            try:
                bm.faces.new(tri)
            except ValueError:
                pass

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    # bm.to_mesh() always resets polygons to flat shading, so re-apply
    # smooth shading here, every single rebuild, rather than relying on
    # a one-off Object > Shade Smooth click that gets wiped out the next
    # time the mesh regenerates (e.g. on every timeline scrub).
    mesh.polygons.foreach_set("use_smooth", [props.use_smooth] * len(mesh.polygons))

    mesh.update()
    if min_r == float("inf"):
        min_r = 0.0
    return min_r, max_r


# ---------------------------------------------------------------------------
# MATERIALS
#
# Two color modes:
#   LATITUDE - bakes a fixed gradient by the *original* sphere latitude
#              (theta) into vertex colors. Stays attached to the same
#              "patch" of surface throughout the eversion.
#   RADIAL   - a live node shader that colors by each point's current
#              distance from the object's center, blue (core) -> green
#              -> yellow (the stretched-out arm tips) - this is what
#              reproduces the look of the reference poster, since the
#              poster's color follows the *current* shape, not the
#              original sphere coordinate. The Map Range node's bounds
#              are driven by custom properties on the object
#              ("ev_radius_min" / "ev_radius_max") that build_mesh()
#              refreshes every regenerate, so the gradient always uses
#              the full color range no matter how far the arms currently
#              reach.
# ---------------------------------------------------------------------------

MATERIAL_NAME_LATITUDE = MATERIAL_NAME + "_Latitude"
MATERIAL_NAME_RADIAL = MATERIAL_NAME + "_Radial"

GRADIENT_STOPS = (
    (0.00, (0.05, 0.30, 0.75, 1.0)),   # blue
    (0.50, (0.20, 0.70, 0.35, 1.0)),   # green
    (1.00, (0.95, 0.85, 0.15, 1.0)),   # yellow
)


def _add_color_ramp(nt, ramp_node):
    ramp_node.color_ramp.elements[0].position = GRADIENT_STOPS[0][0]
    ramp_node.color_ramp.elements[0].color = GRADIENT_STOPS[0][1]
    ramp_node.color_ramp.elements[1].position = GRADIENT_STOPS[2][0]
    ramp_node.color_ramp.elements[1].color = GRADIENT_STOPS[2][1]
    mid = ramp_node.color_ramp.elements.new(GRADIENT_STOPS[1][0])
    mid.color = GRADIENT_STOPS[1][1]


def _driven(socket, obj, prop_name):
    """Add a scripted driver: socket.default_value = obj[prop_name]."""
    fcurve = socket.driver_add("default_value")
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    drv.expression = "r"
    var = drv.variables.new()
    var.name = "r"
    var.type = 'SINGLE_PROP'
    target = var.targets[0]
    target.id_type = 'OBJECT'
    target.id = obj
    target.data_path = '["%s"]' % prop_name


def _build_latitude_material():
    mat = bpy.data.materials.new(MATERIAL_NAME_LATITUDE)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Latitude"
    attr.attribute_type = 'GEOMETRY'
    out.location = (300, 0)
    bsdf.location = (0, 0)
    attr.location = (-300, 0)
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    try:
        bsdf.inputs["Roughness"].default_value = 0.35
    except KeyError:
        pass
    return mat


def _build_radial_material(obj):
    mat = bpy.data.materials.new(MATERIAL_NAME_RADIAL)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    objinfo = nt.nodes.new("ShaderNodeObjectInfo")
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = 'SUBTRACT'
    length = nt.nodes.new("ShaderNodeVectorMath")
    length.operation = 'LENGTH'
    maprange = nt.nodes.new("ShaderNodeMapRange")
    maprange.inputs["To Min"].default_value = 0.0
    maprange.inputs["To Max"].default_value = 1.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    _add_color_ramp(nt, ramp)

    out.location = (700, 0)
    bsdf.location = (450, 0)
    ramp.location = (200, 0)
    maprange.location = (-50, 0)
    length.location = (-250, 0)
    sub.location = (-450, 0)
    geo.location = (-650, 100)
    objinfo.location = (-650, -100)

    nt.links.new(geo.outputs["Position"], sub.inputs[0])
    nt.links.new(objinfo.outputs["Location"], sub.inputs[1])
    nt.links.new(sub.outputs["Vector"], length.inputs[0])
    nt.links.new(length.outputs["Value"], maprange.inputs["Value"])
    nt.links.new(maprange.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    try:
        bsdf.inputs["Roughness"].default_value = 0.35
    except KeyError:
        pass

    _driven(maprange.inputs["From Min"], obj, "ev_radius_min")
    _driven(maprange.inputs["From Max"], obj, "ev_radius_max")
    return mat


def ensure_material(obj, props):
    if props.color_mode == 'RADIAL':
        mat = bpy.data.materials.get(MATERIAL_NAME_RADIAL)
        if mat is None:
            mat = _build_radial_material(obj)
    else:
        mat = bpy.data.materials.get(MATERIAL_NAME_LATITUDE)
        if mat is None:
            mat = _build_latitude_material()

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def regenerate(context):
    props = context.scene.eversion_props
    obj = bpy.data.objects.get(OBJECT_NAME)
    if obj is None:
        mesh = bpy.data.meshes.new(OBJECT_NAME + "_Mesh")
        obj = bpy.data.objects.new(OBJECT_NAME, mesh)
        context.collection.objects.link(obj)
    min_r, max_r = build_mesh(obj.data, props)
    # Keep From Max strictly greater than From Min so the Map Range node
    # (driven from these) never divides by zero, e.g. at progress=0/1
    # where the shape is a perfectly round sphere (min_r == max_r).
    obj["ev_radius_min"] = min_r
    obj["ev_radius_max"] = max(max_r, min_r + 1e-4)
    ensure_material(obj, props)
    obj.show_wire = props.show_wire
    obj.show_all_edges = props.show_wire
    return obj


# ---------------------------------------------------------------------------
# PROPERTIES
# ---------------------------------------------------------------------------

def _update_and_regenerate(self, context):
    if context.scene.eversion_props.live_update:
        regenerate(context)


class SphereEversionProps(bpy.types.PropertyGroup):
    n_arms: bpy.props.IntProperty(
        name="Arms (n)", description="n=2 gives the classic 4-armed quadrifolium "
        "eversion; n=3 gives the (non-orientable) Boy-surface variant; higher n "
        "gives more arms in the pucker/twist phase",
        default=2, min=2, max=6, update=_update_and_regenerate)
    Q: bpy.props.FloatProperty(
        name="Q", description="Controls the twist range t in [-1/Q, 1/Q]. "
        "Must stay below 1", default=0.66, min=0.2, max=0.9, update=_update_and_regenerate)
    progress: bpy.props.FloatProperty(
        name="Progress", description="0 = round sphere, 1 = sphere turned "
        "inside out, 0.5 = symmetric halfway (twist) model",
        default=0.0, min=0.0, max=1.0, update=_update_and_regenerate)
    resolution_theta: bpy.props.IntProperty(
        name="Rings", default=64, min=8, max=300, update=_update_and_regenerate)
    resolution_phi: bpy.props.IntProperty(
        name="Segments", default=128, min=8, max=500, update=_update_and_regenerate)
    pole_epsilon: bpy.props.FloatProperty(
        name="Pole Clamp", description="Keeps theta away from the exact poles "
        "(cos(theta)^n sits in a denominator there)",
        default=0.02, min=0.0005, max=0.3, precision=4, update=_update_and_regenerate)
    alpha_epsilon: bpy.props.FloatProperty(
        name="Alpha Clamp", description="Keeps alpha away from exactly 0 at the "
        "wormhole-inversion phase boundaries (removable singularity)",
        default=0.01, min=0.0005, max=0.2, precision=4, update=_update_and_regenerate)
    radius_scale: bpy.props.FloatProperty(
        name="Scale", default=2.0, min=0.01, max=100.0, update=_update_and_regenerate)
    show_wire: bpy.props.BoolProperty(
        name="Wireframe Overlay", default=True, update=_update_and_regenerate)
    use_smooth: bpy.props.BoolProperty(
        name="Smooth Shading", description="Keep the surface smooth-shaded. "
        "Reapplied on every rebuild so it never reverts to flat after the "
        "first frame", default=True, update=_update_and_regenerate)
    color_mode: bpy.props.EnumProperty(
        name="Coloring",
        description="LATITUDE bakes a fixed color per original sphere "
        "latitude, tied to that patch of surface throughout the eversion. "
        "RADIAL is a live shader colored by current distance from the "
        "object's center (matches the reference poster - core stays blue, "
        "stretched-out arms go yellow), and auto-rescales every frame",
        items=[
            ('RADIAL', "Radial (center to boundary)", "Live shader, distance from center"),
            ('LATITUDE', "Latitude (baked)", "Fixed per original sphere latitude"),
        ],
        default='RADIAL', update=_update_and_regenerate)
    live_update: bpy.props.BoolProperty(
        name="Live Update", description="Regenerate the mesh immediately when "
        "a parameter changes", default=True)

    animate: bpy.props.BoolProperty(
        name="Drive Progress From Timeline", default=False,
        description="On every frame change, set Progress from the current "
        "frame mapped between Frame Start and Frame End")
    frame_start: bpy.props.IntProperty(name="Frame Start", default=1)
    frame_end: bpy.props.IntProperty(name="Frame End", default=250)


# ---------------------------------------------------------------------------
# OPERATORS
# ---------------------------------------------------------------------------

class MESH_OT_eversion_generate(bpy.types.Operator):
    bl_idname = "mesh.sphere_eversion_generate"
    bl_label = "Generate / Update Sphere Eversion"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = regenerate(context)
        context.view_layer.objects.active = obj
        obj.select_set(True)
        return {'FINISHED'}


class MESH_OT_eversion_set_progress(bpy.types.Operator):
    bl_idname = "mesh.sphere_eversion_set_progress"
    bl_label = "Set Progress"
    bl_options = {'REGISTER', 'UNDO'}

    value: bpy.props.FloatProperty(default=0.0)

    def execute(self, context):
        context.scene.eversion_props.progress = self.value
        regenerate(context)
        return {'FINISHED'}


class MESH_OT_eversion_bake_keyframes(bpy.types.Operator):
    bl_idname = "mesh.sphere_eversion_bake_keyframes"
    bl_label = "Bake Progress Keyframes"
    bl_description = ("Insert Progress keyframes at Frame Start (0.0) and "
                       "Frame End (1.0) with linear interpolation, and rebuild "
                       "the mesh at each timeline frame in that range so the "
                       "eversion plays back / renders correctly without the "
                       "live handler")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.eversion_props
        scene = context.scene
        f0, f1 = props.frame_start, props.frame_end
        if f1 <= f0:
            self.report({'ERROR'}, "Frame End must be greater than Frame Start")
            return {'CANCELLED'}

        orig_frame = scene.frame_current
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            props.progress = (f - f0) / (f1 - f0)
            regenerate(context)
            obj = bpy.data.objects.get(OBJECT_NAME)
            obj.data.shape_keys  # no-op guard
        scene.frame_set(orig_frame)
        self.report({'INFO'}, f"Baked mesh for frames {f0}-{f1}. "
                               "Note: this rebuilds geometry directly per frame "
                               "(no shape keys); use with a Freeze/Cache or "
                               "keep the live handler enabled during playback.")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# FRAME CHANGE HANDLER
# ---------------------------------------------------------------------------

@persistent
def eversion_frame_change_handler(scene):
    props = getattr(scene, "eversion_props", None)
    if props is None or not props.animate:
        return
    f0, f1 = props.frame_start, props.frame_end
    if f1 <= f0:
        return
    frame = max(f0, min(f1, scene.frame_current))
    t = (frame - f0) / (f1 - f0)
    if abs(t - props.progress) > 1e-9:
        props.progress = t
        obj = bpy.data.objects.get(OBJECT_NAME)
        if obj is not None:
            build_mesh(obj.data, props)


# ---------------------------------------------------------------------------
# UI PANEL
# ---------------------------------------------------------------------------

class VIEW3D_PT_sphere_eversion(bpy.types.Panel):
    bl_label = "Sphere Eversion"
    bl_idname = "VIEW3D_PT_sphere_eversion"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Eversion"

    def draw(self, context):
        layout = self.layout
        props = context.scene.eversion_props

        col = layout.column(align=True)
        col.operator("mesh.sphere_eversion_generate", icon='MESH_UVSPHERE')
        col.prop(props, "live_update")

        box = layout.box()
        box.label(text="Progress", icon='TIME')
        box.prop(props, "progress", slider=True)
        row = box.row(align=True)
        row.operator("mesh.sphere_eversion_set_progress", text="Sphere").value = 0.0
        row.operator("mesh.sphere_eversion_set_progress", text="Halfway").value = 0.5
        row.operator("mesh.sphere_eversion_set_progress", text="Inside-Out").value = 1.0

        box = layout.box()
        box.label(text="Shape Parameters", icon='MOD_SIMPLEDEFORM')
        box.prop(props, "n_arms")
        box.prop(props, "Q")
        box.prop(props, "radius_scale")

        box = layout.box()
        box.label(text="Resolution & Precision", icon='MESH_GRID')
        box.prop(props, "resolution_theta")
        box.prop(props, "resolution_phi")
        box.prop(props, "pole_epsilon")
        box.prop(props, "alpha_epsilon")

        box = layout.box()
        box.label(text="Appearance", icon='SHADING_RENDERED')
        box.prop(props, "color_mode")
        row = box.row(align=True)
        row.prop(props, "use_smooth", toggle=True, icon='MOD_SMOOTH')
        row.prop(props, "show_wire", toggle=True, icon='MOD_WIREFRAME')

        box = layout.box()
        box.label(text="Animation", icon='ANIM')
        box.prop(props, "animate")
        row = box.row(align=True)
        row.prop(props, "frame_start")
        row.prop(props, "frame_end")
        box.operator("mesh.sphere_eversion_bake_keyframes", icon='RENDER_ANIMATION')


# ---------------------------------------------------------------------------
# REGISTRATION
# ---------------------------------------------------------------------------

classes = (
    SphereEversionProps,
    MESH_OT_eversion_generate,
    MESH_OT_eversion_set_progress,
    MESH_OT_eversion_bake_keyframes,
    VIEW3D_PT_sphere_eversion,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.eversion_props = bpy.props.PointerProperty(type=SphereEversionProps)
    if eversion_frame_change_handler not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(eversion_frame_change_handler)


def unregister():
    if eversion_frame_change_handler in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(eversion_frame_change_handler)
    del bpy.types.Scene.eversion_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
