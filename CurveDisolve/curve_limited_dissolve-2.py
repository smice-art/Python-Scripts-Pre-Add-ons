bl_info = {
    "name": "Curve Limited Dissolve",
    "author": "Claude",
    "version": (1, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Curve Tools  |  N-panel when curve selected",
    "description": "Removes curve points whose direction change is below a threshold angle — like Limited Dissolve for meshes, but for Bezier/Poly curves.",
    "category": "Curve",
}

import bpy
import math
from mathutils import Vector


# ─────────────────────────────────────────────
#  Core algorithm
# ─────────────────────────────────────────────

def angle_between(v1: Vector, v2: Vector) -> float:
    """Return angle in degrees between two vectors. Returns 0 if either is zero-length."""
    if v1.length_squared < 1e-12 or v2.length_squared < 1e-12:
        return 0.0
    return math.degrees(v1.angle(v2))


def dissolve_curve_points(curve_obj, angle_threshold_deg: float, only_selected: bool) -> int:
    """
    Walk every spline of curve_obj and remove points whose local
    direction-change is smaller than angle_threshold_deg degrees.
    Returns the number of points removed.
    """
    curve = curve_obj.data
    removed_total = 0

    # We iterate over a snapshot of splines because we modify the list
    splines_snapshot = list(curve.splines)

    for spline in splines_snapshot:

        # ── BEZIER ───────────────────────────────────────────────
        if spline.type == 'BEZIER':
            pts = spline.bezier_points
            n = len(pts)
            if n < 3:
                continue

            keep = [True] * n
            # Never dissolve the first and last point of an open spline
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
                continue
            removed_total += removed

            # Snapshot data for kept points
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

            cyclic = spline.use_cyclic_u
            new_spline = curve.splines.new('BEZIER')
            new_spline.bezier_points.add(len(kept_data) - 1)
            for j, d in enumerate(kept_data):
                bp = new_spline.bezier_points[j]
                bp.co                = d["co"]
                bp.handle_left       = d["handle_left"]
                bp.handle_right      = d["handle_right"]
                bp.handle_left_type  = d["handle_left_type"]
                bp.handle_right_type = d["handle_right_type"]
                bp.tilt              = d["tilt"]
                bp.radius            = d["radius"]
            new_spline.use_cyclic_u = cyclic
            curve.splines.remove(spline)

        # ── POLY ─────────────────────────────────────────────────
        elif spline.type == 'POLY':
            pts = spline.points
            n = len(pts)
            if n < 3:
                continue

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
                continue
            removed_total += removed

            # Snapshot (x, y, z, w) tuples
            kept_coords = [tuple(pts[i].co) for i in kept_indices]

            cyclic = spline.use_cyclic_u
            new_spline = curve.splines.new('POLY')
            new_spline.points.add(len(kept_coords) - 1)  # new() already gives 1 point
            for j, co in enumerate(kept_coords):
                new_spline.points[j].co = co
            new_spline.use_cyclic_u = cyclic
            curve.splines.remove(spline)

        else:
            # NURBS — skip silently
            pass

    return removed_total


# ─────────────────────────────────────────────
#  Operator
# ─────────────────────────────────────────────

class CURVE_OT_limited_dissolve(bpy.types.Operator):
    bl_idname  = "curve.limited_dissolve"
    bl_label   = "Curve Limited Dissolve"
    bl_description = (
        "Remove curve points whose direction change is below the angle threshold. "
        "Works like Limited Dissolve for meshes."
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

        if context.mode == 'EDIT_CURVE':
            bpy.ops.object.editmode_toggle()
            obj = context.active_object
            removed = dissolve_curve_points(obj, threshold_deg, self.only_selected)
            bpy.ops.object.editmode_toggle()
            self.report({'INFO'}, f"Dissolved {removed} point(s) from '{obj.name}'.")

        else:  # OBJECT mode
            targets = (
                [o for o in context.selected_objects if o.type == 'CURVE']
                if self.apply_to_all
                else (
                    [context.active_object]
                    if context.active_object and context.active_object.type == 'CURVE'
                    else []
                )
            )
            total = 0
            for obj in targets:
                total += dissolve_curve_points(obj, threshold_deg, False)
            self.report({'INFO'}, f"Dissolved {total} point(s) across {len(targets)} object(s).")

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "angle_threshold", slider=True)
        if context.mode == 'EDIT_CURVE':
            layout.prop(self, "only_selected")
        else:
            layout.prop(self, "apply_to_all")


# ─────────────────────────────────────────────
#  N-panel (always-visible sidebar panel)
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
#  Object-mode menu hook  (safe: no edit-curve menu)
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
