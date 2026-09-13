import bpy
import math

def create_scherk_node_group():
    group_name = "Scherk_Collins_GeoNodes"
    
    # Remove existing group to avoid duplicates on multiple runs
    if group_name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[group_name])
        
    tree = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')

    #this script build a geomety node setup for a "scherk like" object in blender
    
    # -------------------------------------------------------------------
    # 1. Setup Interface (Blender 4.0+ API)
    # -------------------------------------------------------------------
    tree.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    
    in_res_u = tree.interface.new_socket(name="Resolution U", in_out='INPUT', socket_type='NodeSocketInt')
    in_res_u.default_value = 128
    in_res_u.min_value = 8
    
    in_res_v = tree.interface.new_socket(name="Resolution V", in_out='INPUT', socket_type='NodeSocketInt')
    in_res_v.default_value = 256
    in_res_v.min_value = 8
    
    in_radius = tree.interface.new_socket(name="Tower Radius", in_out='INPUT', socket_type='NodeSocketFloat')
    in_radius.default_value = 1.5
    
    in_height = tree.interface.new_socket(name="Tower Height", in_out='INPUT', socket_type='NodeSocketFloat')
    in_height.default_value = 13.5
    
    in_branches = tree.interface.new_socket(name="Branches (Noids)", in_out='INPUT', socket_type='NodeSocketInt')
    in_branches.default_value = 4
    
    in_segments = tree.interface.new_socket(name="Segments (Holes)", in_out='INPUT', socket_type='NodeSocketInt')
    in_segments.default_value = 4
    
    in_hole_size = tree.interface.new_socket(name="Hole Threshold", in_out='INPUT', socket_type='NodeSocketFloat')
    in_hole_size.default_value = 0.001
    
    in_twist = tree.interface.new_socket(name="Twist (Degrees)", in_out='INPUT', socket_type='NodeSocketFloat')
    in_twist.default_value = 0.0
    
    in_bend = tree.interface.new_socket(name="Toroidal Bend (Degrees)", in_out='INPUT', socket_type='NodeSocketFloat')
    in_bend.default_value = 0.0
    
    in_subdiv = tree.interface.new_socket(name="Subdivision Levels", in_out='INPUT', socket_type='NodeSocketInt')
    in_subdiv.default_value = 2
    
    in_smooth = tree.interface.new_socket(name="Smooth Shading", in_out='INPUT', socket_type='NodeSocketBool')
    in_smooth.default_value = True

    # -------------------------------------------------------------------
    # Helper functions to speed up node creation and linking
    # -------------------------------------------------------------------
    nodes = tree.nodes
    links = tree.links

    def new_node(idname, location=(0,0), **kwargs):
        node = nodes.new(idname)
        node.location = location
        for key, value in kwargs.items():
            setattr(node, key, value)
        return node
        
    def math_node(op, loc, in0, in1=None):
        node = new_node('ShaderNodeMath', loc, operation=op)
        if isinstance(in0, tuple): links.new(in0[0], node.inputs[0])
        else: node.inputs[0].default_value = in0
        
        if in1 is not None:
            if isinstance(in1, tuple): links.new(in1[0], node.inputs[1])
            else: node.inputs[1].default_value = in1
        return node

    # -------------------------------------------------------------------
    # 2. Node Generation & Logic Routing
    # -------------------------------------------------------------------
    group_in = new_node('NodeGroupInput', (-1200, 0))
    group_out = new_node('NodeGroupOutput', (1600, 0))
    
    # Base Grid (Maintains strict vertex management, avoiding torus primitives)
    grid = new_node('GeometryNodeMeshGrid', (-1000, 200))
    grid.inputs["Size X"].default_value = 1.0
    grid.inputs["Size Y"].default_value = 1.0
    
    links.new(group_in.outputs["Resolution U"], grid.inputs["Vertices X"])
    links.new(group_in.outputs["Resolution V"], grid.inputs["Vertices Y"])
    
    # Get Grid Coordinates (X and Y map from -0.5 to 0.5)
    pos_in = new_node('GeometryNodeInputPosition', (-1000, -200))
    sep_xyz = new_node('ShaderNodeSeparateXYZ', (-800, -200))
    links.new(pos_in.outputs["Position"], sep_xyz.inputs["Vector"])
    
    # Map X to U (0 to 2*pi)
    x_add = math_node('ADD', (-600, -100), (sep_xyz.outputs["X"],), 0.5)
    u_val = math_node('MULTIPLY', (-450, -100), (x_add.outputs["Value"],), 2 * math.pi)
    
    # Map Y to V (Segments)
    y_mult_seg = math_node('MULTIPLY', (-600, -300), (sep_xyz.outputs["Y"],), (group_in.outputs["Segments (Holes)"],))
    v_val = math_node('MULTIPLY', (-450, -300), (y_mult_seg.outputs["Value"],), 2 * math.pi)
    
    # Flat Branch Logic: cos(Branches * U)
    branch_mult = math_node('MULTIPLY', (-250, 100), (u_val.outputs["Value"],), (group_in.outputs["Branches (Noids)"],))
    branch_cos = math_node('COSINE', (-100, 100), (branch_mult.outputs["Value"],))
    
    # Z Factor: cos(V)
    z_cos = math_node('COSINE', (-250, -100), (v_val.outputs["Value"],))
    
    # Pinch mapping: pinch = (1.0 - branch_cos) * 0.5
    pinch_sub = math_node('SUBTRACT', (100, 100), 1.0, (branch_cos.outputs["Value"],))
    pinch = math_node('MULTIPLY', (250, 100), (pinch_sub.outputs["Value"],), 0.5)
    
    # Hole Depth: depth = (1.0 + z_cos) * 0.5
    depth_add = math_node('ADD', (100, -100), 1.0, (z_cos.outputs["Value"],))
    depth = math_node('MULTIPLY', (250, -100), (depth_add.outputs["Value"],), 0.5)
    
    # Dynamic Radius: R = Tower_Radius * (1.0 - (pinch * depth))
    pinch_depth = math_node('MULTIPLY', (450, 50), (pinch.outputs["Value"],), (depth.outputs["Value"],))
    r_sub = math_node('SUBTRACT', (600, 50), 1.0, (pinch_depth.outputs["Value"],))
    radius = math_node('MULTIPLY', (750, 50), (group_in.outputs["Tower Radius"],), (r_sub.outputs["Value"],))
    
    # Hole Deletion Mask: (radius < hole_size)
    hole_compare = math_node('LESS_THAN', (900, -150), (radius.outputs["Value"],), (group_in.outputs["Hole Threshold"],))
    
    # Calculate X, Y, Z Positions
    u_cos = math_node('COSINE', (600, -300), (u_val.outputs["Value"],))
    u_sin = math_node('SINE', (600, -450), (u_val.outputs["Value"],))
    
    pos_x = math_node('MULTIPLY', (900, -300), (radius.outputs["Value"],), (u_cos.outputs["Value"],))
    pos_y = math_node('MULTIPLY', (900, -450), (radius.outputs["Value"],), (u_sin.outputs["Value"],))
    pos_z = math_node('MULTIPLY', (900, -600), (sep_xyz.outputs["Y"],), (group_in.outputs["Tower Height"],))
    
    comb_xyz = new_node('ShaderNodeCombineXYZ', (1100, -400))
    links.new(pos_x.outputs["Value"], comb_xyz.inputs["X"])
    links.new(pos_y.outputs["Value"], comb_xyz.inputs["Y"])
    links.new(pos_z.outputs["Value"], comb_xyz.inputs["Z"])
    
    # Apply Initial Shape
    set_pos_1 = new_node('GeometryNodeSetPosition', (1300, 200))
    links.new(grid.outputs["Mesh"], set_pos_1.inputs["Geometry"])
    links.new(comb_xyz.outputs["Vector"], set_pos_1.inputs["Position"])
    
    # Delete Holes
    del_geo = new_node('GeometryNodeDeleteGeometry', (1500, 200))
    links.new(set_pos_1.outputs["Geometry"], del_geo.inputs["Geometry"])
    links.new(hole_compare.outputs["Value"], del_geo.inputs["Selection"])
    
    # Twist
    twist_rad = math_node('RADIANS', (1300, -100), (group_in.outputs["Twist (Degrees)"],))
    twist_factor = math_node('MULTIPLY', (1500, -100), (sep_xyz.outputs["Y"],), (twist_rad.outputs["Value"],))
    
    set_pos_2 = new_node('GeometryNodeSetPosition', (1700, 200))
    vec_rot_twist = new_node('ShaderNodeVectorRotate', (1700, -100), rotation_type='Z_AXIS')
    
    pos_in_2 = new_node('GeometryNodeInputPosition', (1500, -300))
    links.new(pos_in_2.outputs["Position"], vec_rot_twist.inputs["Vector"])
    links.new(twist_factor.outputs["Value"], vec_rot_twist.inputs["Angle"])
    
    links.new(del_geo.outputs["Geometry"], set_pos_2.inputs["Geometry"])
    links.new(vec_rot_twist.outputs["Vector"], set_pos_2.inputs["Position"])
    
    # Toroidal Bend
    bend_rad = math_node('RADIANS', (1700, -400), (group_in.outputs["Toroidal Bend (Degrees)"],))
    bend_factor = math_node('MULTIPLY', (1900, -400), (sep_xyz.outputs["Y"],), (bend_rad.outputs["Value"],))
    
    # Radius of Curvature (R_c = Height / Bend Angle). Avoid division by zero.
    bend_safe = math_node('MAXIMUM', (1700, -600), (bend_rad.outputs["Value"],), 0.0001)
    r_curve = math_node('DIVIDE', (1900, -600), (group_in.outputs["Tower Height"],), (bend_safe.outputs["Value"],))
    
    # Offset X by R_c
    pos_in_3 = new_node('GeometryNodeInputPosition', (1900, -200))
    sep_xyz_2 = new_node('ShaderNodeSeparateXYZ', (2100, -200))
    links.new(pos_in_3.outputs["Position"], sep_xyz_2.inputs["Vector"])
    
    add_rc = math_node('ADD', (2300, -200), (sep_xyz_2.outputs["X"],), (r_curve.outputs["Value"],))
    comb_xyz_2 = new_node('ShaderNodeCombineXYZ', (2500, -200))
    links.new(add_rc.outputs["Value"], comb_xyz_2.inputs["X"])
    links.new(sep_xyz_2.outputs["Y"], comb_xyz_2.inputs["Y"])
    links.new(sep_xyz_2.outputs["Z"], comb_xyz_2.inputs["Z"])
    
    vec_rot_bend = new_node('ShaderNodeVectorRotate', (2700, -200), rotation_type='Y_AXIS')
    links.new(comb_xyz_2.outputs["Vector"], vec_rot_bend.inputs["Vector"])
    links.new(bend_factor.outputs["Value"], vec_rot_bend.inputs["Angle"])
    
    # Subtract R_c to center
    sep_xyz_3 = new_node('ShaderNodeSeparateXYZ', (2900, -200))
    links.new(vec_rot_bend.outputs["Vector"], sep_xyz_3.inputs["Vector"])
    sub_rc = math_node('SUBTRACT', (3100, -200), (sep_xyz_3.outputs["X"],), (r_curve.outputs["Value"],))
    comb_xyz_3 = new_node('ShaderNodeCombineXYZ', (3300, -200))
    links.new(sub_rc.outputs["Value"], comb_xyz_3.inputs["X"])
    links.new(sep_xyz_3.outputs["Y"], comb_xyz_3.inputs["Y"])
    links.new(sep_xyz_3.outputs["Z"], comb_xyz_3.inputs["Z"])
    
    # Mix between twisted linear shape and toroidal bent shape
    mix_bend = new_node('ShaderNodeMix', (3500, -100), data_type='VECTOR')
    bend_check = math_node('GREATER_THAN', (3300, -400), (group_in.outputs["Toroidal Bend (Degrees)"],), 0.001)
    links.new(bend_check.outputs["Value"], mix_bend.inputs["Factor"])
    links.new(pos_in_3.outputs["Position"], mix_bend.inputs["A"])
    links.new(comb_xyz_3.outputs["Vector"], mix_bend.inputs["B"])

    set_pos_3 = new_node('GeometryNodeSetPosition', (3700, 200))
    links.new(set_pos_2.outputs["Geometry"], set_pos_3.inputs["Geometry"])
    
    # Using outputs[0] for the Mix Node as Blender 4.x consolidates "Result" to index 0
    links.new(mix_bend.outputs[0], set_pos_3.inputs["Position"]) 
    
    # Clean Topology Smoothing
    subdiv = new_node('GeometryNodeSubdivisionSurface', (3900, 200))
    links.new(set_pos_3.outputs["Geometry"], subdiv.inputs["Mesh"])
    links.new(group_in.outputs["Subdivision Levels"], subdiv.inputs["Level"])
    
    shade_smooth = new_node('GeometryNodeSetShadeSmooth', (4100, 200))
    links.new(subdiv.outputs["Mesh"], shade_smooth.inputs["Geometry"])
    links.new(group_in.outputs["Smooth Shading"], shade_smooth.inputs["Shade Smooth"])
    
    # Output
    links.new(shade_smooth.outputs["Geometry"], group_out.inputs["Geometry"])
    
    return tree

# -------------------------------------------------------------------
# Apply to scene
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Build the Node Tree
    scherk_tree = create_scherk_node_group()
    
    # Create the host object
    me = bpy.data.meshes.new("Scherk_GeoMesh")
    obj = bpy.data.objects.new("Scherk_Tower_Procedural", me)
    bpy.context.collection.objects.link(obj)
    
    # Assign Modifier
    mod = obj.modifiers.new(name="Scherk Generator", type='NODES')
    mod.node_group = scherk_tree
    
    # Select Object
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)