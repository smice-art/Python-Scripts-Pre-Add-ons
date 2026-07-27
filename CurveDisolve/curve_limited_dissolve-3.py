bl_info = {
    "name": "Curve Limited Dissolve",
    "author": "Claude",
    "version": (1, 2, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Curve Tools  |  Object Menu (Object Mode)",
    "description": "Removes curve points whose direction change is below a threshold angle — like Limited Dissolve for meshes, but for Bezier/Poly curves. Also merges duplicate/overlapping points.",
    "category": "Curve",
}

import bpy
import math
from mathutils import Vector


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def angle_between(v1: Vector, v2: Vector) -> float:
    """Return angle in degrees between two vectors. Returns 180 if either is zero-length
    (zero-length means the two adjacent points are identical — treat as straight)."""
    if v1.length_squared < 1e-12 or v2.length_squared < 1e-12:
        return 180.0   # ← was 0.0 before; now correctly treated as "no turn = dissolve"
    return math.degrees(v1.angle(v2))


# ─────────────────────────────────────────────
#  Per-spline helpers
# ─────────────────────────────────────────────

def rebuild_bezier(curve, spline, kept_data):
    cyclic = spline.use_cyclic_u
    new_sp = curve.splines.new('BEZIER')
    new_sp.bezier_points.add(len(kept_data) - 1)
    for j, d in enumerate(kept_data):
        bp = new_sp.bezier_points[j]
        bp.co                = d["co"]
        bp.handle_left       = d["handle_left"]
        bp.handle_right      = d["handle_right"]
        bp.handle_left_type  = d["handle_left_type"]
        bp.handle_right_type = d["handle_right_type"]
        bp.tilt              = d["tilt"]
        bp.radius            = d["radius"]
    new_sp.use_cyclic_u = cyclic
    curve.splines.remove(spline)


def rebuild_poly(curve, spline, kept_coords):
    cyclic = spline.use_cyclic_u
    new_sp = curve.splines.new('POLY')
    new_sp.points.add(len(kept_coords) - 1)
    for j, co in enumerate(kept_coords):
        new_sp.points[j].co = co
    new_sp.use_cyclic_u = cyclic
    curve.splines.remove(spline)


# ─────────────────────────────────────────────
#  Step 1 — merge duplicate / nearby points
# ─────────────────────────────────────────────

def merge_nearby_points_bezier(curve, spline, merge_dist: float) -> int:
    """Collapse runs of points that are within merge_dist of each other into one."""
    pts = spline.bezier_points
    n = len(pts)
    if n < 2:
        return 0

    coords = [p.co.copy() for p in pts]
    kept_data = []
    removed = 0

    i = 0
    while i < n:
        # Start a new group at i
        group_start = i
        j = i + 1
        while j < n and (coords[j] - coords[i]).length < merge_dist:
            j += 1
        # Representative = middle of the group
        rep = group_start + (j - group_start) // 2
        p = pts[rep]
        kept_data.append({
            "co":               p.co.copy(),
            "handle_left":      p.handle_left.copy(),
            "handle_right":     p.handle_right.copy(),
            "handle_left_type": p.handle_left_type,
            "handle_right_type":p.handle_right_type,
            "tilt":             p.tilt,
            "radius":           p.radius,
        })
        removed += (j - group_start - 1)
        i = j

    if removed > 0:
        rebuild_bezier(curve, spline, kept_data)
    return removed


def merge_nearby_points_poly(curve, spline, merge_dist: float) -> int:
    pts = spline.points
    n = len(pts)
    if n < 2:
        return 0

    coords = [pts[k].co.xyz.copy() for k in range(n)]
    kept_coords = []
    removed = 0

    i = 0
    while i < n:
        group_start = i
        j = i + 1
        while j < n and (coords[j] - coords[i]).length < merge_dist:
            j += 1
        rep = group_start + (j - group_start) // 2
        kept_coords.append(tuple(pts[rep].co))
        removed += (j - group_start - 1)
        i = j

    if removed > 0:
        rebuild_poly(curve, spline, kept_coords)
    return removed


# ─────────────────────────────────────────────
#  Step 2 — angle-based dissolve
# ─────────────────────────────────────────────

def dissolve_by_angle_bezier(curve, spline, angle_threshold_deg: float,
                              only_selected: bool) -> int:
    pts = spline.bezier_points
    n = len(pts)
    if n < 3:
        return 0

    keep = [True] * n
    for i in range(1, n - 1):
        if only_selected and not pts[i].select_control_point:
            continue
        v_in  = pts[i].co - pts[i - 1].co
        v_out = pts[i + 1].co - pts[i].co
        if angle_between(v_in, v_out) < angle_threshold_deg:
            keep[i] = False

    kept_indices = [i for i in range(n) if keep[i]]
    removed = n - len(kept_indices)
    if removed == 0:
        return 0

    kept_data = []
    for i in kept_indices:
        p = pts[i]
        kept_data.append({
            "co":               p.co.copy(),
            "handle_left":      p.handle_left.copy(),
            "handle_right":     p.handle_right.copy(),
            "handle_left_type": p.handle_left_type,
            "handle_right_type":p.handle_right_type,
            "tilt":             p.tilt,
            "radius":           p.radius,
        })
    rebuild_bezier(curve, spline, kept_data)
    return removed


def dissolve_by_angle_poly(curve, spline, angle_threshold_deg: float,
                            only_selected: bool) -> int:
    pts = spline.points
    n = len(pts)
    if n < 3:
        return 0

    keep = [True] * n
    for i in range(1, n - 1):
        if only_selected and not pts[i].select:
            continue
        v_in  = pts[i].co.xyz - pts[i - 1].co.xyz
        v_out = pts[i + 1].co.xyz - pts[i].co.xyz
        if angle_between(v_in, v_out) < angle_threshold_deg:
            keep[i] = False

    kept_indices = [i for i in range(n) if keep[i]]
    removed = n - len(kept_indices)
    if removed == 0:
        return 0

    kept_coords = [tuple(pts[i].co) for i in kept_indices]
    rebuild_poly(curve, spline, kept_coords)
    return removed


# ─────────────────────────────────────────────
#  Main entry point
# ─────────────────────────────────────────────

def process_curve(curve_obj, angle_threshold_deg: float, merge_dist: float,
                  only_selected: bool) -> tuple:
    """Returns (points_merged, points_dissolved)."""
    curve = curve_obj.data
    merged_total   = 0
    dissolved_total = 0

    # Two passes — snapshot splines each time because the list changes
    # Pass 1: merge nearby / duplicate points
    if merge_dist > 0:
        for spline in list(curve.splines):
            if spline.type == 'BEZIER':
                merged_total += merge_nearby_points_bezier(curve, spline, merge_dist)
            elif spline.type == 'POLY':
                merged_total += merge_nearby_points_poly(curve, spline, merge_dist)

    # Pass 2: angle dissolve
    for spline in list(curve.splines):
        if spline.type == 'BEZIER':
            dissolved_total += dissolve_by_angle_bezier(
                curve, spline, angle_threshold_deg, only_selected)
        elif spline.type == 'POLY':
            dissolved_total += dissolve_by_angle_poly(
                curve, spline, angle_threshold_deg, only_selected)

    return merged_total, dissolved_total


# ─────────────────────────────────────────────
#  Operator
# ─────────────────────────────────────────────

class CURVE_OT_limited_dissolve(bpy.types.Operator):
    bl_idname  = "curve.limited_dissolve"
    bl_label   = "Curve Limited Dissolve"
    bl_description = (
        "Remove curve points whose direction change is below the angle threshold, "
        "and optionally merge duplicate/overlapping points first."
    )
    bl_options = {'REGISTER', 'UNDO'}

    angle_threshold: bpy.props.FloatProperty(
        name="Max Angle",
        description="Points with a direction change BELOW this angle are dissolved",
        default=math.radians(5.0),
        min=0.0,
        max=math.radians(180.0),
        step=10,
        precision=1,
        subtype='ANGLE',
    )

    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        description="Points closer than this distance are merged first (0 = disabled). "
                    "Use a small value like 0.001 to clean up duplicate/overlapping points.",
        default=0.001,
        min=0.0,
        max=10.0,
        step=0.1,
        precision=4,
        subtype='DISTANCE',
    )

    only_selected: bpy.props.BoolProperty(
        name="Only Selected Points",
        description="Operate only on currently selected control points (Edit Mode only)",
        default=False,
    )

    apply_to_all: bpy.props.BoolProperty(
        name="All Selected Objects",
        description="Apply to all selected curve objects (Object Mode)",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_CURVE':
            return context.active_object and context.active_object.type == 'CURVE'
        elif context.mode == 'OBJECT':
            return any(o.type == 'CURVE' for o in context.selected_objects)
        return False

    def execute(self, context):
        threshold_deg = math.degrees(self.angle_threshold)
        merge_dist    = self.merge_distance

        if context.mode == 'EDIT_CURVE':
            bpy.ops.object.editmode_toggle()
            obj = context.active_object
            merged, dissolved = process_curve(obj, threshold_deg, merge_dist, self.only_selected)
            bpy.ops.object.editmode_toggle()
            self.report({'INFO'},
                f"'{obj.name}': merged {merged}, dissolved {dissolved} point(s).")

        else:
            targets = (
                [o for o in context.selected_objects if o.type == 'CURVE']
                if self.apply_to_all
                else (
                    [context.active_object]
                    if context.active_object and context.active_object.type == 'CURVE'
                    else []
                )
            )
            total_m = total_d = 0
            for obj in targets:
                m, d = process_curve(obj, threshold_deg, merge_dist, False)
                total_m += m
                total_d += d
            self.report({'INFO'},
                f"Merged {total_m}, dissolved {total_d} point(s) across {len(targets)} object(s).")

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "merge_distance")
        layout.prop(self, "angle_threshold", slider=True)
        if context.mode == 'EDIT_CURVE':
            layout.prop(self, "only_selected")
        else:
            layout.prop(self, "apply_to_all")


# ─────────────────────────────────────────────
#  N-panel
# ─────────────────────────────────────────────

class CURVE_PT_limited_dissolve(bpy.types.Panel):
    bl_label       = "Curve Limited Dissolve"
    bl_idname      = "CURVE_PT_limited_dissolve"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "Curve Tools"

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_CURVE':
            return context.active_object and context.active_object.type == 'CURVE'
        return (
            context.mode == 'OBJECT'
            and any(o.type == 'CURVE' for o in context.selected_objects)
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Simplify by angle:", icon='MOD_SIMPLIFY')
        layout.operator("curve.limited_dissolve", text="Run Dissolve", icon='X')


# ─────────────────────────────────────────────
#  Object-mode menu hook
# ─────────────────────────────────────────────

def menu_func_object(self, context):
    if any(o.type == 'CURVE' for o in context.selected_objects):
        self.layout.operator(
            CURVE_OT_limited_dissolve.bl_idname,
            text="Curve Limited Dissolve",
            icon='MOD_SIMPLIFY',
        )


# ─────────────────────────────────────────────
#  Register / Unregister
# ─────────────────────────────────────────────

classes = [
    CURVE_OT_limited_dissolve,
    CURVE_PT_limited_dissolve,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(menu_func_object)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.VIEW3D_MT_object.remove(menu_func_object)


if __name__ == "__main__":
    register()
