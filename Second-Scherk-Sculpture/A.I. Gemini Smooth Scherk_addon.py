import bpy
import bmesh
import math
from math import sin, cos, pi
import random

# -------------------------------------------------------------------
# Material Setup Function
# -------------------------------------------------------------------
def setup_scherk_material(obj, theme_choice):
    mat_name = "Scherk_Glossy_Mat"
    mat = bpy.data.materials.get(mat_name)
    
    if not mat:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
    else:
        mat.node_tree.nodes.clear()

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Create Core Nodes
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (400, 0)

    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = (100, 0)
    principled.inputs['Roughness'].default_value = 0.15  # Glossy finish
    principled.inputs['Metallic'].default_value = 0.2

    # Color Merging Setup
    mix_color = nodes.new(type='ShaderNodeMix')
    mix_color.data_type = 'RGBA'
    mix_color.blend_type = 'MIX'
    mix_color.location = (-150, 0)
    
    noise = nodes.new(type='ShaderNodeTexNoise')
    noise.location = (-350, 100)
    noise.inputs['Scale'].default_value = 2.5
    noise.inputs['Detail'].default_value = 4.0

    # Link Nodes
    links.new(noise.outputs['Fac'], mix_color.inputs['Factor'])
    links.new(mix_color.outputs['Result'], principled.inputs['Base Color'])
    links.new(principled.outputs['BSDF'], output_node.inputs['Surface'])

    # Define Theme Colors
    if theme_choice == 'RANDOM':
        color1 = (random.random(), random.random(), random.random(), 1.0)
        color2 = (random.random(), random.random(), random.random(), 1.0)
    elif theme_choice == 'GOLD':
        color1 = (0.8, 0.6, 0.1, 1.0)
        color2 = (0.4, 0.2, 0.05, 1.0)
        principled.inputs['Metallic'].default_value = 1.0
    elif theme_choice == 'PEARL':
        color1 = (0.9, 0.9, 0.95, 1.0)
        color2 = (0.8, 0.7, 0.8, 1.0)
        principled.inputs['Roughness'].default_value = 0.05
    elif theme_choice == 'OCEAN':
        color1 = (0.02, 0.15, 0.4, 1.0)
        color2 = (0.05, 0.5, 0.6, 1.0)
    
    mix_color.inputs[6].default_value = color1 # Color 1 (A)
    mix_color.inputs[7].default_value = color2 # Color 2 (B)

    # Assign to object
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


# -------------------------------------------------------------------
# Update Callback for Auto-Update
# -------------------------------------------------------------------
def update_scherk(self, context):
    if self.auto_update:
        bpy.ops.mesh.generate_scherk()

# -------------------------------------------------------------------
# Property Group for N-Panel Adjustments
# -------------------------------------------------------------------
class ScherkProperties(bpy.types.PropertyGroup):
    auto_update: bpy.props.BoolProperty(
        name="Auto-Update",
        description="Automatically update the mesh when values change",
        default=True
    )
    use_smooth: bpy.props.BoolProperty(
        name="Smooth Shading",
        description="Apply smooth shading to the mesh",
        default=True,
        update=update_scherk
    )
    subdiv_levels: bpy.props.IntProperty(
        name="Smooth Holes (Subsurf)",
        description="Subdivision levels to smooth out the hole topology",
        default=2, min=0, max=4,
        update=update_scherk
    )
    material_theme: bpy.props.EnumProperty(
        name="Material",
        description="Select a glossy color theme",
        items=[
            ('RANDOM', "Randomized", "Random merged colors"),
            ('GOLD', "Glossy Gold", "Metallic gold mix"),
            ('PEARL', "White Pearl", "Smooth glossy pearl"),
            ('OCEAN', "Ocean Blue", "Deep blue merge")
        ],
        default='RANDOM',
        update=update_scherk
    )
    resolution_u: bpy.props.IntProperty(
        name="Resolution U",
        description="Grid resolution along the radial axis",
        default=96, min=8, max=512,
        update=update_scherk
    )
    resolution_v: bpy.props.IntProperty(
        name="Resolution V",
        description="Grid resolution along the vertical axis",
        default=128, min=8, max=512,
        update=update_scherk
    )
    tower_radius: bpy.props.FloatProperty(
        name="Tower Radius",
        description="Base radius of the tower",
        default=2.16, min=0.1, max=100.0,
        update=update_scherk
    )
    tower_height: bpy.props.FloatProperty(
        name="Tower Height",
        description="Overall height of the tower",
        default=40.0, min=0.1, max=100.0,
        update=update_scherk
    )
    segments: bpy.props.IntProperty(
        name="Segments (Holes)",
        description="Number of hole segments separated along the Z-axis",
        default=6, min=1, max=20,
        update=update_scherk
    )
    noid_branches: bpy.props.IntProperty(
        name="Branches (Noids)",
        description="Number of symmetrical branches (e.g., 4-angle object)",
        default=6, min=2, max=12,
        update=update_scherk
    )
    hole_size: bpy.props.FloatProperty(
        name="Hole Threshold",
        description="Adjusts how wide the holes open up",
        default=0.1, min=0.01, max=2.0,
        update=update_scherk
    )
    twist_angle: bpy.props.FloatProperty(
        name="Twist (Degrees)",
        description="Overall twist applied to the tower",
        default=0.0, min=-1440.0, max=1440.0,
        update=update_scherk
    )
    bend_angle: bpy.props.FloatProperty(
        name="Toroidal Bend (Degrees)",
        description="Bend the tower into a torus (360 = fully closed)",
        default=360.0, min=0.0, max=360.0,
        update=update_scherk
    )

# -------------------------------------------------------------------
# Operator to Generate the Parametric Geometry
# -------------------------------------------------------------------
class MESH_OT_generate_scherk(bpy.types.Operator):
    bl_idname = "mesh.generate_scherk"
    bl_label = "Generate Scherk Tower"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.scherk_props
        
        # Target a single object to prevent duplicates
        obj_name = "Scherk_Tower"
        if obj_name in bpy.data.objects:
            obj = bpy.data.objects[obj_name]
            me = obj.data
        else:
            me = bpy.data.meshes.new("Scherk_Mesh")
            obj = bpy.data.objects.new(obj_name, me)
            context.collection.objects.link(obj)
            
        bm = bmesh.new()
        verts = []

        twist_rad = math.radians(props.twist_angle)
        bend_rad = math.radians(props.bend_angle)
        
        N = props.noid_branches
        H = props.segments
        res_u = props.resolution_u
        res_v = props.resolution_v
        
        # 1. Generate Vertices 
        for i in range(res_u):
            u_frac = i / res_u 
            u = u_frac * 2 * pi 
            
            for j in range(res_v):
                v_frac = j / (res_v - 1)
                v = (v_frac - 0.5) * H * 2 * pi
                
                angle_factor = cos(N * u)
                z_factor = cos(v)
                
                pinch = (1.0 - angle_factor) * 0.5
                hole_depth = (1.0 + z_factor) * 0.5
                
                r = props.tower_radius * (1.0 - (pinch * hole_depth))
                
                x = r * cos(u)
                y = r * sin(u)
                z = (v_frac - 0.5) * props.tower_height
                
                # 2. Apply Twist
                norm_z = (v_frac - 0.5) 
                current_twist = norm_z * twist_rad
                
                x_twisted = x * cos(current_twist) - y * sin(current_twist)
                y_twisted = x * sin(current_twist) + y * cos(current_twist)
                x, y = x_twisted, y_twisted
                
                # 3. Apply Toroidal Bend 
                if props.bend_angle > 0.001:
                    R_c = props.tower_height / bend_rad
                    torus_angle = norm_z * bend_rad
                    
                    current_radius = R_c + x
                    
                    final_x = current_radius * cos(torus_angle) - R_c
                    final_y = y
                    final_z = current_radius * sin(torus_angle)
                else:
                    final_x = x
                    final_y = y
                    final_z = z

                verts.append(bm.verts.new((final_x, final_y, final_z)))

        bm.verts.ensure_lookup_table()

        # 4. Generate Faces and Cut Holes
        for i in range(res_u):
            next_i = (i + 1) % res_u 
            
            for j in range(res_v - 1):
                u_mid = ((i + 0.5) / res_u) * 2 * pi
                v_mid = (((j + 0.5) / (res_v - 1)) - 0.5) * H * 2 * pi
                
                angle_factor = cos(N * u_mid)
                z_factor = cos(v_mid)
                pinch = (1.0 - angle_factor) * 0.5
                hole_depth = (1.0 + z_factor) * 0.5
                
                r_mid = props.tower_radius * (1.0 - (pinch * hole_depth))
                
                if r_mid < props.hole_size:
                    continue 

                v1 = verts[i * res_v + j]
                v2 = verts[next_i * res_v + j]
                v3 = verts[next_i * res_v + (j + 1)]
                v4 = verts[i * res_v + (j + 1)]
                
                try:
                    bm.faces.new((v1, v2, v3, v4))
                except ValueError:
                    pass

        bm.to_mesh(me)
        bm.free()

        # Shading & Modifiers
        for p in me.polygons:
            p.use_smooth = props.use_smooth
            
        mod_name = "Scherk_Smoother"
        mod = obj.modifiers.get(mod_name)
        if not mod:
            mod = obj.modifiers.new(mod_name, 'SUBSURF')
        mod.levels = props.subdiv_levels
        mod.render_levels = props.subdiv_levels

        # Apply Material
        setup_scherk_material(obj, props.material_theme)

        me.update()
        return {'FINISHED'}

# -------------------------------------------------------------------
# N-Panel User Interface
# -------------------------------------------------------------------
class VIEW3D_PT_scherk_panel(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Scherk Art'
    bl_label = "Scherk-Collins Generator"

    def draw(self, context):
        layout = self.layout
        props = context.scene.scherk_props

        row = layout.row()
        row.prop(props, "auto_update")
        row.prop(props, "use_smooth")
        
        layout.prop(props, "subdiv_levels")
        layout.prop(props, "material_theme")
        
        layout.separator()

        col = layout.column(align=True)
        col.label(text="Size:")
        col.prop(props, "tower_radius")
        col.prop(props, "tower_height")
        
        layout.separator()

        col = layout.column(align=True)
        col.label(text="Grid Resolution:")
        col.prop(props, "resolution_u", text="U (Radial)")
        col.prop(props, "resolution_v", text="V (Vertical)")
        
        layout.separator()
        
        col = layout.column(align=True)
        col.label(text="Topology:")
        col.prop(props, "noid_branches")
        col.prop(props, "segments")
        col.prop(props, "hole_size")
        
        layout.separator()
        
        col = layout.column(align=True)
        col.label(text="Deformation:")
        col.prop(props, "twist_angle")
        col.prop(props, "bend_angle")

        layout.separator()
        
        if not props.auto_update:
            layout.operator("mesh.generate_scherk", text="Update Mesh", icon='MESH_GRID')

# -------------------------------------------------------------------
# Registration
# -------------------------------------------------------------------
classes = (
    ScherkProperties,
    MESH_OT_generate_scherk,
    VIEW3D_PT_scherk_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scherk_props = bpy.props.PointerProperty(type=ScherkProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.scherk_props

if __name__ == "__main__":
    register()