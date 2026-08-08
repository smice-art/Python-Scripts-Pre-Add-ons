"""
Organic Random Thickness — Geometry Nodes builder
---------------------------------------------------
Builds a reusable Geometry Nodes group that takes any curve and outputs 
a tube mesh whose radius varies organically along the curve's length.

Updates:
  - Fixed KeyError by forcing the script to clear and rebuild the Node 
    Group interface on every run, preventing missing socket errors.
"""

import bpy


GROUP_NAME = "Organic Random Thickness Simple"


def build_interface(node_group):
    """Define the group's exposed inputs/outputs (Blender 4.x+ API)."""
    iface = node_group.interface

    iface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')

    # Noise Parameters
    s = iface.new_socket("Noise Scale", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 5.0
    s.min_value = -10.0

    s = iface.new_socket("Noise Detail", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 2.0
    s.min_value = 0.0
    s.max_value = 15.0

    s = iface.new_socket("Noise Roughness", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.5
    s.min_value = 0.0
    s.max_value = 1.0

    s = iface.new_socket("Random Seed", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0

    # Map Range Input Mapping
    s = iface.new_socket("From Min", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.32

    s = iface.new_socket("From Max", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.9

    # Thickness Output Range
    s = iface.new_socket("Thickness Min", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.02
    s.min_value = 0.0

    s = iface.new_socket("Thickness Max", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.62
    s.min_value = 0.0

    # Mesh & Material Parameters
    s = iface.new_socket("Profile Resolution", in_out='INPUT', socket_type='NodeSocketInt')
    s.default_value = 24
    s.min_value = 3
    s.max_value = 180

    s = iface.new_socket("Shade Smooth", in_out='INPUT', socket_type='NodeSocketBool')
    s.default_value = True

    s = iface.new_socket("Material", in_out='INPUT', socket_type='NodeSocketMaterial')

    iface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')


def build_nodes(node_group):
    nodes = node_group.nodes
    links = node_group.links
    nodes.clear()

    group_in = nodes.new('NodeGroupInput')
    group_in.location = (-900, 0)

    group_out = nodes.new('NodeGroupOutput')
    group_out.location = (1100, 0)

    # --- Spline Parameter & Noise Setup ---
    spline_param = nodes.new('GeometryNodeSplineParameter')
    spline_param.location = (-700, -250)

    combine_xyz = nodes.new('ShaderNodeCombineXYZ')
    combine_xyz.location = (-500, -250)

    noise_tex = nodes.new('ShaderNodeTexNoise')
    noise_tex.location = (-300, -150)
    noise_tex.noise_dimensions = '4D'

    map_range = nodes.new('ShaderNodeMapRange')
    map_range.location = (-100, -150)

    # --- Named Attribute & Switch Setup ---
    named_attr = nodes.new('GeometryNodeInputNamedAttribute')
    named_attr.data_type = 'FLOAT'
    named_attr.inputs['Name'].default_value = "strength"
    named_attr.location = (-100, -350)

    switch_node = nodes.new('GeometryNodeSwitch')
    switch_node.input_type = 'FLOAT'
    switch_node.inputs['False'].default_value = 1.0
    switch_node.location = (150, -350)

    # --- Curve & Mesh Setup ---
    set_radius = nodes.new('GeometryNodeSetCurveRadius')
    set_radius.location = (150, 100)

    curve_circle = nodes.new('GeometryNodeCurvePrimitiveCircle')
    curve_circle.location = (150, -150)
    curve_circle.inputs['Radius'].default_value = 1.0

    curve_to_mesh = nodes.new('GeometryNodeCurveToMesh')
    curve_to_mesh.location = (400, 0)
    curve_to_mesh.inputs['Fill Caps'].default_value = True

    shade_smooth = nodes.new('GeometryNodeSetShadeSmooth')
    shade_smooth.location = (650, 0)

    set_material = nodes.new('GeometryNodeSetMaterial')
    set_material.location = (850, 0)

    # --- Links ---
    # Spline to Noise
    links.new(spline_param.outputs['Factor'], combine_xyz.inputs['X'])
    links.new(combine_xyz.outputs['Vector'], noise_tex.inputs['Vector'])

    # Noise parameters
    links.new(group_in.outputs['Noise Scale'], noise_tex.inputs['Scale'])
    links.new(group_in.outputs['Noise Detail'], noise_tex.inputs['Detail'])
    links.new(group_in.outputs['Noise Roughness'], noise_tex.inputs['Roughness'])
    links.new(group_in.outputs['Random Seed'], noise_tex.inputs['W'])

    # Map Range connections using indices
    links.new(noise_tex.outputs['Fac'], map_range.inputs[0])          # Value
    links.new(group_in.outputs['From Min'], map_range.inputs[1])      # From Min
    links.new(group_in.outputs['From Max'], map_range.inputs[2])      # From Max
    links.new(group_in.outputs['Thickness Min'], map_range.inputs[3]) # To Min
    links.new(group_in.outputs['Thickness Max'], map_range.inputs[4]) # To Max
    links.new(map_range.outputs['Result'], set_radius.inputs['Radius'])

    # Named Attribute -> Switch logic
    links.new(named_attr.outputs['Exists'], switch_node.inputs['Switch'])
    links.new(named_attr.outputs['Attribute'], switch_node.inputs['True'])

    # Geometry Pipeline
    links.new(group_in.outputs['Geometry'], set_radius.inputs['Curve'])
    links.new(group_in.outputs['Profile Resolution'], curve_circle.inputs['Resolution'])
    links.new(set_radius.outputs['Curve'], curve_to_mesh.inputs['Curve'])
    links.new(curve_circle.outputs['Curve'], curve_to_mesh.inputs['Profile Curve'])

    links.new(curve_to_mesh.outputs['Mesh'], shade_smooth.inputs['Geometry'])
    links.new(group_in.outputs['Shade Smooth'], shade_smooth.inputs['Shade Smooth'])

    # Set Material Pipeline
    links.new(shade_smooth.outputs['Geometry'], set_material.inputs['Geometry'])
    links.new(switch_node.outputs['Output'], set_material.inputs['Selection'])
    links.new(group_in.outputs['Material'], set_material.inputs['Material'])

    links.new(set_material.outputs['Geometry'], group_out.inputs['Geometry'])


def get_or_create_node_group():
    if GROUP_NAME in bpy.data.node_groups:
        node_group = bpy.data.node_groups[GROUP_NAME]
        node_group.nodes.clear()
        node_group.interface.clear()  # FIX: Clear old interface so it gets rebuilt!
    else:
        node_group = bpy.data.node_groups.new(GROUP_NAME, 'GeometryNodeTree')
        
    build_interface(node_group) # Always rebuild the interface now
    build_nodes(node_group)
    return node_group


def apply_to_selected_object():
    obj = bpy.context.active_object
    if obj is None or obj.type != 'CURVE':
        raise RuntimeError(
            "Select a curve object first (e.g. add a Curve Circle: "
            "Shift+A > Curve > Circle), then run this script again."
        )

    # Check and convert splines to BEZIER if they are not already
    for spline in obj.data.splines:
        if spline.type != 'BEZIER':
            spline.type = 'BEZIER'

    node_group = get_or_create_node_group()

    # Apply modifier if not already present
    if GROUP_NAME not in obj.modifiers:
        mod = obj.modifiers.new(name=GROUP_NAME, type='NODES')
        mod.node_group = node_group
        print(f"Added '{GROUP_NAME}' Geometry Nodes modifier to '{obj.name}' and verified Bézier splines.")
    else:
        print(f"Updated '{GROUP_NAME}' on '{obj.name}'.")


if __name__ == "__main__":
    apply_to_selected_object()