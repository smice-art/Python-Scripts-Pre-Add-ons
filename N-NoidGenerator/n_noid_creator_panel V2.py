import bpy
import math

# ======================================================================
#      1. The Core Calculation Function (Unchanged)
# ======================================================================
def calculate_noid_coords(u, v, n, k1=None, k2=None):
    """
    Calculates the x, y, z coordinates for a point on the n-noid surface.
    """
    if k1 is None:
        k1 = 2 * n - 3
    if k2 is None:
        k2 = n - 2
    
    term1_x = -(u**-1) * math.cos(v)
    term2_x = -(u**k1 / k1) * math.cos(k1 * v) if k1 != 0 else 0
    x = term1_x + term2_x
    
    term1_y = -(u**-1) * math.sin(v)
    term2_y = -(u**k1 / k1) * math.sin(k1 * v) if k1 != 0 else 0
    y = term1_y + term2_y

    if k2 == 0:
        z = 2 * math.log(u) if u > 0 else 0
    else:
        z = (2 / k2) * (u**k2) * math.cos(k2 * v)
        
    return (x, y, z)

def generate_noid_mesh_data(props):
    """
    Generates vertex and face data based on the provided properties.
    This keeps the mesh generation logic separate from the operator.
    """
    verts = []
    faces = []
    
    # Read properties from the provided property group
    n = props.num_legs
    scale = props.scale
    u_res = props.u_resolution
    v_res = props.v_resolution
    u_min = props.u_min
    u_max = props.u_max
    v_min = 0.0
    v_max = 2 * math.pi

    # Determine k1 and k2 from UI overrides or formula
    if props.use_custom_k:
        k1 = props.k1
        k2 = props.k2
    else:
        k1 = 2 * n - 3
        k2 = n - 2

    u_step = (u_max - u_min) / (u_res - 1)
    v_step = (v_max - v_min) / v_res

    for j in range(v_res):
        v = v_min + j * v_step
        for i in range(u_res):
            u = u_min + i * u_step
            x, y, z = calculate_noid_coords(u, v, n, k1, k2)
            verts.append((x * scale, y * scale, z * scale))

    for j in range(v_res):
        for i in range(u_res - 1):
            p1 = j * u_res + i
            p2 = j * u_res + (i + 1)
            p3 = ((j + 1) % v_res) * u_res + (i + 1)
            p4 = ((j + 1) % v_res) * u_res + i
            faces.append((p1, p2, p3, p4))
            
    return verts, faces


# ======================================================================
#      2. The Property Group to Store Settings
# ======================================================================
def update_num_legs(self, context):
    """Automatically recalculate k1 and k2 when N (Legs) changes."""
    if not self.use_custom_k:
        self.k1 = float(2 * self.num_legs - 3)
        self.k2 = float(self.num_legs - 2)

def update_custom_k_toggle(self, context):
    """Reset k1 and k2 to standard formula when custom K is turned off."""
    if not self.use_custom_k:
        self.k1 = float(2 * self.num_legs - 3)
        self.k2 = float(self.num_legs - 2)

class NoidProperties(bpy.types.PropertyGroup):
    """Stores the settings for the N-noid generator."""
    
    num_legs: bpy.props.IntProperty(
        name="N (Legs)",
        description="Number of catenoidal ends",
        default=4, min=2, max=40,
        update=update_num_legs
    )
    scale: bpy.props.FloatProperty(
        name="Scale",
        description="Overall scale of the mesh",
        default=0.8, min=0.01, soft_max=20.0
    )
    use_custom_k: bpy.props.BoolProperty(
        name="Custom K Values",
        description="Override the standard formulas for k1 and k2",
        default=False,
        update=update_custom_k_toggle
    )
    k1: bpy.props.FloatProperty(
        name="k1 Parameter",
        description="Custom k1 parameter (Standard formula: 2*N - 3)",
        default=3.0, soft_min=-10.0, soft_max=40.0
    )
    k2: bpy.props.FloatProperty(
        name="k2 Parameter",
        description="Custom k2 parameter (Standard formula: N - 2)",
        default=1.0, soft_min=-10.0, soft_max=40.0
    )
    u_resolution: bpy.props.IntProperty(
        name="U Resolution",
        description="Vertices along the U direction (radial)",
        default=64, min=4, max=1512
    )
    v_resolution: bpy.props.IntProperty(
        name="V Resolution",
        description="Vertices along the V direction (angular)",
        default=256, min=4, max=1512
    )
    u_min: bpy.props.FloatProperty(
        name="U Min",
        description="Starting value for U (> 0)",
        default=0.4, min=0.01, soft_max=5.0
    )
    u_max: bpy.props.FloatProperty(
        name="U Max",
        description="Ending value for U",
        default=1.25, min=0.1, soft_max=10.0
    )

# ======================================================================
#      3. The Operator to Create/Update the Mesh
# ======================================================================
class OBJECT_OT_generate_n_noid(bpy.types.Operator):
    """Create or update an N-noid mesh based on scene properties"""
    bl_idname = "mesh.generate_n_noid"
    bl_label = "Generate N-noid"
    bl_options = {'REGISTER', 'UNDO'}

    update: bpy.props.BoolProperty(
        name="Update",
        description="Update the active object instead of creating a new one",
        default=False
    )

    def execute(self, context):
        props = context.scene.noid_tool_props
        verts, faces = generate_noid_mesh_data(props)
        mesh_name = f"{props.num_legs}-noid"
        
        # Check if we should update the active object
        if self.update and context.active_object and context.active_object.type == 'MESH':
            obj = context.active_object
            mesh = obj.data
            mesh.clear_geometry() # Clear existing data
        else:
            mesh = bpy.data.meshes.new(name=mesh_name)
            obj = bpy.data.objects.new(mesh_name, mesh)
            context.collection.objects.link(obj)
            context.view_layer.objects.active = obj
            obj.select_set(True)

        mesh.from_pydata(verts, [], faces)
        mesh.update()
        return {'FINISHED'}


# ======================================================================
#      4. The Panel that Draws the UI in the N-Panel
# ======================================================================
class VIEW3D_PT_n_noid_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport N-Panel"""
    bl_label = "N-noid Creator"
    bl_idname = "VIEW3D_PT_n_noid"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'N-noid' # This creates the tab in the N-Panel

    def draw(self, context):
        layout = self.layout
        props = context.scene.noid_tool_props # Get our custom properties

        layout.label(text="Parameters:")
        col_legs = layout.column(align=True)
        col_legs.enabled = not props.use_custom_k  # Greys out N when custom K is active
        col_legs.prop(props, "num_legs")
        
        col_scale = layout.column(align=True)
        col_scale.prop(props, "scale")
        
        layout.separator()
        layout.label(text="K Parameters (Surface Shape):")
        col = layout.column(align=True)
        col.prop(props, "use_custom_k")
        if props.use_custom_k:
            col.prop(props, "k1")
            col.prop(props, "k2")

        layout.separator()
        layout.label(text="Resolution:")
        col = layout.column(align=True)
        col.prop(props, "u_resolution")
        col.prop(props, "v_resolution")

        layout.separator()
        layout.label(text="Domain (U value):")
        col = layout.column(align=True)
        col.prop(props, "u_min")
        col.prop(props, "u_max")

        layout.separator()
        
        # --- Operator Buttons ---
        # Button to create a new object
        create_op = layout.operator("mesh.generate_n_noid", text="Create New N-noid", icon='ADD')
        create_op.update = False

        # Button to update the currently selected object
        update_op = layout.operator("mesh.generate_n_noid", text="Update Active", icon='FILE_REFRESH')
        update_op.update = True


# ======================================================================
#      5. Registration
# ======================================================================
classes = (
    NoidProperties,
    OBJECT_OT_generate_n_noid,
    VIEW3D_PT_n_noid_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # Attach our property group to the scene
    bpy.types.Scene.noid_tool_props = bpy.props.PointerProperty(type=NoidProperties)

def unregister():
    # Important to delete the scene property before unregistering the class
    del bpy.types.Scene.noid_tool_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()