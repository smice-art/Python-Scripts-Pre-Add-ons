"""
Organic Random Thickness — Geometry Nodes builder (Blender 4.0+ Safe)
---------------------------------------------------
Builds a reusable Geometry Nodes group that takes any curve and outputs 
a tube mesh whose radius varies organically along the curve's length.

Updates in this version:
  - Fixed Blender 4.0+ API AttributeError on the Capture Attribute node.
  - Replaced Capture nodes with temporary Store Named Attribute nodes 
    (which are API-stable across Blender versions) to capture U and V.
"""

import bpy
import math


GROUP_NAME = "Organic Random Thickness"


def build_interface(node_group):
    """Define the group's exposed inputs/outputs."""
    iface = node_group.interface

    iface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')

    # Animation & Noise Parameters
    s = iface.new_socket("Wobble Speed", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0

    s = iface.new_socket("Noise Scale", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.5
    s.min_value = 0.0

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
    s.default_value = 0.320

    s = iface.new_socket("From Max", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.91

    # Thickness Output Range
    s = iface.new_socket("Thickness Min", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.02
    s.min_value = 0.0

    s = iface.new_socket("Thickness Max", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.32
    s.min_value = 0.0

    # Mesh & Material Parameters
    s = iface.new_socket("Profile Resolution", in_out='INPUT', socket_type='NodeSocketInt')
    s.default_value = 12
    s.min_value = 3
    s.max_value = 64

    s = iface.new_socket("Shade Smooth", in_out='INPUT', socket_type='NodeSocketBool')
    s.default_value = True

    s = iface.new_socket("Material", in_out='INPUT', socket_type='NodeSocketMaterial')

    iface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')


def build_nodes(node_group):
    nodes = node_group.nodes
    links = node_group.links
    nodes.clear()

    group_in = nodes.new('NodeGroupInput')
    group_in.location = (-1200, 0)

    group_out = nodes.new('NodeGroupOutput')
    group_out.location = (1400, 0)

    # --- Spline Parameter & Circular Mapping (Seamless Loop) ---
    spline_param_main = nodes.new('GeometryNodeSplineParameter')
    spline_param_main.location = (-1200, -250)

    math_tau = nodes.new('ShaderNodeMath')
    math_tau.operation = 'MULTIPLY'
    math_tau.inputs[1].default_value = math.tau  # 2 * Pi
    math_tau.location = (-1000, -250)

    math_cos = nodes.new('ShaderNodeMath')
    math_cos.operation = 'COSINE'
    math_cos.location = (-800, -150)

    math_sin = nodes.new('ShaderNodeMath')
    math_sin.operation = 'SINE'
    math_sin.location = (-800, -350)

    combine_xyz_noise = nodes.new('ShaderNodeCombineXYZ')
    combine_xyz_noise.location = (-600, -250)

    # --- Animation Setup (Scene Time) ---
    scene_time = nodes.new('GeometryNodeInputSceneTime')
    scene_time.location = (-800, -550)

    math_time_mult = nodes.new('ShaderNodeMath')
    math_time_mult.operation = 'MULTIPLY'
    math_time_mult.location = (-600, -550)

    math_time_add = nodes.new('ShaderNodeMath')
    math_time_add.operation = 'ADD'
    math_time_add.location = (-400, -550)

    # --- Noise Setup ---
    noise_tex = nodes.new('ShaderNodeTexNoise')
    noise_tex.location = (-300, -250)
    noise_tex.noise_dimensions = '4D'

    map_range = nodes.new('ShaderNodeMapRange')
    map_range.location = (-100, -250)

    # --- UV Temporary Storing Setup (Blender 4.0+ Safe) ---
    store_u = nodes.new('GeometryNodeStoreNamedAttribute')
    store_u.data_type = 'FLOAT'
    store_u.domain = 'POINT'
    store_u.inputs['Name'].default_value = "uv_u"
    store_u.location = (-100, 100)

    curve_circle = nodes.new('GeometryNodeCurvePrimitiveCircle')
    curve_circle.location = (-100, -700)
    curve_circle.inputs['Radius'].default_value = 1.0

    spline_param_profile = nodes.new('GeometryNodeSplineParameter')
    spline_param_profile.location = (-300, -850)

    store_v = nodes.new('GeometryNodeStoreNamedAttribute')
    store_v.data_type = 'FLOAT'
    store_v.domain = 'POINT'
    store_v.inputs['Name'].default_value = "uv_v"
    store_v.location = (150, -700)

    # --- Curve & Mesh Setup ---
    set_radius = nodes.new('GeometryNodeSetCurveRadius')
    set_radius.location = (150, 100)

    curve_to_mesh = nodes.new('GeometryNodeCurveToMesh')
    curve_to_mesh.location = (400, 0)
    curve_to_mesh.inputs['Fill Caps'].default_value = True

    # --- Read Temporary UVs and Combine ---
    read_u = nodes.new('GeometryNodeInputNamedAttribute')
    read_u.data_type = 'FLOAT'
    read_u.inputs['Name'].default_value = "uv_u"
    read_u.location = (150, -200)

    read_v = nodes.new('GeometryNodeInputNamedAttribute')
    read_v.data_type = 'FLOAT'
    read_v.inputs['Name'].default_value = "uv_v"
    read_v.location = (150, -350)

    combine_uv = nodes.new('ShaderNodeCombineXYZ')
    combine_uv.location = (400, -250)

    store_uv = nodes.new('GeometryNodeStoreNamedAttribute')
    store_uv.data_type = 'FLOAT_VECTOR'
    store_uv.domain = 'CORNER'
    store_uv.inputs['Name'].default_value = "UV_Map"
    store_uv.location = (650, 0)

    # --- Strength Attribute Switch ---
    named_attr = nodes.new('GeometryNodeInputNamedAttribute')
    named_attr.data_type = 'FLOAT'
    named_attr.inputs['Name'].default_value = "strength"
    named_attr.location = (400, -500)

    switch_node = nodes.new('GeometryNodeSwitch')
    switch_node.input_type = 'FLOAT'
    switch_node.inputs['False'].default_value = 1.0
    switch_node.location = (650, -450)

    # --- Shading & Material ---
    shade_smooth = nodes.new('GeometryNodeSetShadeSmooth')
    shade_smooth.location = (850, 0)

    set_material = nodes.new('GeometryNodeSetMaterial')
    set_material.location = (1100, 0)

    # ==========================
    # --- LINKS ---
    # ==========================

    # 1. Circular Noise Coordinates
    links.new(spline_param_main.outputs['Factor'], math_tau.inputs[0])
    links.new(math_tau.outputs['Value'], math_cos.inputs[0])
    links.new(math_tau.outputs['Value'], math_sin.inputs[0])
    links.new(math_cos.outputs['Value'], combine_xyz_noise.inputs['X'])
    links.new(math_sin.outputs['Value'], combine_xyz_noise.inputs['Y'])
    links.new(combine_xyz_noise.outputs['Vector'], noise_tex.inputs['Vector'])

    # 2. Animation (Time -> W)
    links.new(scene_time.outputs['Seconds'], math_time_mult.inputs[0])
    links.new(group_in.outputs['Wobble Speed'], math_time_mult.inputs[1])
    links.new(math_time_mult.outputs['Value'], math_time_add.inputs[0])
    links.new(group_in.outputs['Random Seed'], math_time_add.inputs[1])
    links.new(math_time_add.outputs['Value'], noise_tex.inputs['W'])

    # 3. Noise parameters & Range Mapping
    links.new(group_in.outputs['Noise Scale'], noise_tex.inputs['Scale'])
    links.new(group_in.outputs['Noise Detail'], noise_tex.inputs['Detail'])
    links.new(group_in.outputs['Noise Roughness'], noise_tex.inputs['Roughness'])

    links.new(noise_tex.outputs['Fac'], map_range.inputs[0])          
    links.new(group_in.outputs['From Min'], map_range.inputs[1])      
    links.new(group_in.outputs['From Max'], map_range.inputs[2])      
    links.new(group_in.outputs['Thickness Min'], map_range.inputs[3]) 
    links.new(group_in.outputs['Thickness Max'], map_range.inputs[4]) 
    links.new(map_range.outputs['Result'], set_radius.inputs['Radius'])

    # 4. Store Temporary U and V Attributes on Curves
    links.new(group_in.outputs['Geometry'], store_u.inputs['Geometry'])
    links.new(spline_param_main.outputs['Factor'], store_u.inputs['Value'])
    
    links.new(group_in.outputs['Profile Resolution'], curve_circle.inputs['Resolution'])
    links.new(curve_circle.outputs['Curve'], store_v.inputs['Geometry'])
    links.new(spline_param_profile.outputs['Factor'], store_v.inputs['Value'])

    # 5. Geometry Pipeline
    links.new(store_u.outputs['Geometry'], set_radius.inputs['Curve'])
    links.new(set_radius.outputs['Curve'], curve_to_mesh.inputs['Curve'])
    links.new(store_v.outputs['Geometry'], curve_to_mesh.inputs['Profile Curve'])

    # 6. Read back Temporary U/V, Combine, and Store Final UV
    links.new(read_u.outputs[0], combine_uv.inputs['X']) # [0] is the 'Attribute' output
    links.new(read_v.outputs[0], combine_uv.inputs['Y'])
    links.new(curve_to_mesh.outputs['Mesh'], store_uv.inputs['Geometry'])
    links.new(combine_uv.outputs['Vector'], store_uv.inputs['Value'])

    # 7. Named Attribute & Switch logic (Strength selection)
    links.new(named_attr.outputs['Exists'], switch_node.inputs['Switch'])
    links.new(named_attr.outputs[0], switch_node.inputs['True']) # [0] is 'Attribute'

    # 8. Shading & Material Setup
    links.new(store_uv.outputs['Geometry'], shade_smooth.inputs['Geometry'])
    links.new(group_in.outputs['Shade Smooth'], shade_smooth.inputs['Shade Smooth'])
    
    links.new(shade_smooth.outputs['Geometry'], set_material.inputs['Geometry'])
    links.new(switch_node.outputs['Output'], set_material.inputs['Selection'])
    links.new(group_in.outputs['Material'], set_material.inputs['Material'])

    # Final Output
    links.new(set_material.outputs['Geometry'], group_out.inputs['Geometry'])


def get_or_create_node_group():
    if GROUP_NAME in bpy.data.node_groups:
        node_group = bpy.data.node_groups[GROUP_NAME]
        node_group.nodes.clear()
        node_group.interface.clear()  
    else:
        node_group = bpy.data.node_groups.new(GROUP_NAME, 'GeometryNodeTree')
        
    build_interface(node_group)
    build_nodes(node_group)
    return node_group


def apply_to_selected_object():
    obj = bpy.context.active_object
    if obj is None or obj.type != 'CURVE':
        raise RuntimeError(
            "Select a curve object first, then run this script again."
        )

    for spline in obj.data.splines:
        if spline.type != 'BEZIER':
            spline.type = 'BEZIER'

    node_group = get_or_create_node_group()

    if GROUP_NAME not in obj.modifiers:
        mod = obj.modifiers.new(name=GROUP_NAME, type='NODES')
        mod.node_group = node_group
        print(f"Added '{GROUP_NAME}' Geometry Nodes modifier to '{obj.name}'.")
    else:
        print(f"Updated '{GROUP_NAME}' on '{obj.name}'.")


if __name__ == "__main__":
    apply_to_selected_object()