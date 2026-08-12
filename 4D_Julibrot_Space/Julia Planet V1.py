bl_info = {
    "name": "4D Julibrot space",
    "author": "claudio",
    "version": (1, 2),
    "blender": (3, 60, 0),
    "location": "View3D > Sidebar (N) > Julibrot Generator",
    "description": "This tool is a procedural 3D mesh generator ",
    "category": "Add Mesh",
}

import bpy
import bmesh
import math
from bpy.props import FloatProperty, IntProperty, BoolProperty, EnumProperty, PointerProperty

# --- CORE GENERATION LOGIC ---

def get_julibrot_radius(phi, theta, props):
    scale_x = props.scale_x
    scale_y = props.scale_y
    offset_x = props.offset_x
    
    if props.mapping_preset == 'DEFAULT':
        scale_x, scale_y, offset_x = 1.5, 1.5, -0.5
    elif props.mapping_preset == 'CENTERED':
        scale_x, scale_y, offset_x = 1.5, 1.5, 0.0
    elif props.mapping_preset == 'COMPACT':
        scale_x, scale_y, offset_x = 0.8, 0.8, -0.5
    elif props.mapping_preset == 'STRETCH_X':
        scale_x, scale_y, offset_x = 2.5, 1.0, -0.5

    xc = math.sin(theta) * math.cos(phi) * scale_x + offset_x
    yc = math.sin(theta) * math.sin(phi) * scale_y
    zc = complex(xc, yc)
    
    z_height = props.z_height_start
    step = props.step_size
    max_iter = props.max_iter
    
    while z_height >= 0:
        z_iter = complex(z_height, 0)
        escaped = False
        for i in range(max_iter):
            if abs(z_iter) >= 2:
                escaped = True
                break
            z_iter = z_iter**2 + zc
        
        if not escaped:
            return z_height
        z_height -= step
        
    return 0.0


def build_julibrot_planet(context):
    props = context.scene.julibrot_props
    res = props.resolution
    base_r = props.base_radius
    frac_s = props.frac_strength
    shape = props.base_shape

    obj_name = "JulibrotObject"
    obj = context.scene.objects.get(obj_name)
    
    if obj is None:
        mesh_data = bpy.data.meshes.new(obj_name)
        obj = bpy.data.objects.new(obj_name, mesh_data)
        context.collection.objects.link(obj)
    else:
        mesh_data = obj.data
        
    bm = bmesh.new()
    verts = []

    # Topology Mesh Generation
    if shape == 'SPHERE':
        for it in range(res + 1):
            theta = it * math.pi / res
            for ip in range(res + 1):
                phi = ip * 2 * math.pi / res
                h = get_julibrot_radius(phi, theta, props)
                r = base_r + (h * frac_s)
                
                x = r * math.sin(theta) * math.cos(phi)
                y = r * math.sin(theta) * math.sin(phi)
                z = r * math.cos(theta)
                verts.append(bm.verts.new((x, y, z)))

    elif shape == 'TORUS':
        r_major = base_r
        r_minor = props.torus_minor
        for it in range(res + 1):
            u = it * 2 * math.pi / res  # Major loop angle
            for ip in range(res + 1):
                v = ip * 2 * math.pi / res  # Minor loop angle
                
                h = get_julibrot_radius(v, u / 2.0, props)
                disp = h * frac_s
                
                x = (r_major + (r_minor + disp) * math.cos(v)) * math.cos(u)
                y = (r_major + (r_minor + disp) * math.cos(v)) * math.sin(u)
                z = (r_minor + disp) * math.sin(v)
                verts.append(bm.verts.new((x, y, z)))

    elif shape == 'PLANE':
        size = base_r * 2.0
        for it in range(res + 1):
            u = (it / res) - 0.5
            theta = (it / res) * math.pi
            for ip in range(res + 1):
                v = (ip / res) - 0.5
                phi = (ip / res) * 2 * math.pi
                
                h = get_julibrot_radius(phi, theta, props)
                
                x = u * size
                y = v * size
                z = h * frac_s
                verts.append(bm.verts.new((x, y, z)))

    elif shape == 'CUBE':
        for it in range(res + 1):
            theta = it * math.pi / res
            for ip in range(res + 1):
                phi = ip * 2 * math.pi / res
                
                dx = math.sin(theta) * math.cos(phi)
                dy = math.sin(theta) * math.sin(phi)
                dz = math.cos(theta)
                
                max_d = max(abs(dx), abs(dy), abs(dz), 1e-6)
                
                h = get_julibrot_radius(phi, theta, props)
                
                bx = (dx / max_d) * base_r
                by = (dy / max_d) * base_r
                bz = (dz / max_d) * base_r
                
                x = bx + (dx * h * frac_s)
                y = by + (dy * h * frac_s)
                z = bz + (dz * h * frac_s)
                verts.append(bm.verts.new((x, y, z)))

    # Grid Quad Face Generation
    bm.verts.ensure_lookup_table()
    stride = res + 1
    for it in range(res):
        for ip in range(res):
            v1 = verts[it * stride + ip]
            v2 = verts[(it + 1) * stride + ip]
            v3 = verts[(it + 1) * stride + (ip + 1)]
            v4 = verts[it * stride + (ip + 1)]
            try:
                bm.faces.new((v1, v2, v3, v4))
            except:
                pass

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bm.to_mesh(mesh_data)
    bm.free()
    mesh_data.update()

    # Material Setup
    mat_name = "JulibrotCore"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            if 'Base Color' in bsdf.inputs:
                bsdf.inputs['Base Color'].default_value = (0.05, 0.05, 0.2, 1.0)
            if 'Metallic' in bsdf.inputs:
                bsdf.inputs['Metallic'].default_value = 0.9
            if 'Roughness' in bsdf.inputs:
                bsdf.inputs['Roughness'].default_value = 0.2
            coat_input = bsdf.inputs.get('Coat Weight') or bsdf.inputs.get('Coat')
            if coat_input:
                coat_input.default_value = 1.0

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    context.view_layer.objects.active = obj
    obj.select_set(False)
    bpy.ops.object.shade_smooth()


# --- UPDATE CALLBACK ---

def update_julibrot(self, context):
    if self.auto_update:
        build_julibrot_planet(context)


# --- UI PROPERTY GROUP ---

class JulibrotProperties(bpy.types.PropertyGroup):
    base_shape: EnumProperty(
        name="Base Shape",
        description="Select top level geometry manifold",
        items=[
            ('SPHERE', "Sphere", "Spherical coordinate mapping", 'MESH_UVSPHERE', 0),
            ('CUBE', "Cube", "Box projected mapping", 'MESH_CUBE', 1),
            ('PLANE', "Plane", "Flat horizontal grid mapping", 'MESH_PLANE', 2),
            ('TORUS', "Torus", "Toroidal ring mapping", 'MESH_TORUS', 3),
        ],
        default='SPHERE',
        update=update_julibrot
    )
    torus_minor: FloatProperty(
        name="Minor Radius",
        description="Torus inner tube radius",
        default=0.8, min=0.05,
        update=update_julibrot
    )
    resolution: IntProperty(
        name="Resolution",
        description="Grid density (N x N)",
        default=120, min=10, max=400,
        update=update_julibrot
    )
    base_radius: FloatProperty(
        name="Base Radius",
        description="Base geometric radius / scale",
        default=2.0, min=0.1,
        update=update_julibrot
    )
    frac_strength: FloatProperty(
        name="Fractal Strength",
        description="Surface displacement amplitude",
        default=1.2,
        update=update_julibrot
    )
    max_iter: IntProperty(
        name="Max Iterations",
        description="Fractal loop escape threshold",
        default=12, min=1, max=100,
        update=update_julibrot
    )
    mapping_preset: EnumProperty(
        name="Structure Preset",
        description="Preset mappings from coordinates to complex plane",
        items=[
            ('DEFAULT', "Default (Standard Julibrot)", "Scale 1.5, Offset -0.5"),
            ('CENTERED', "Centered Origin", "Scale 1.5, Offset 0.0"),
            ('COMPACT', "High Density", "Scale 0.8, Offset -0.5"),
            ('STRETCH_X', "X-Stretched", "Scale X: 2.5, Y: 1.0"),
            ('CUSTOM', "Custom Mapping", "Manual scale and offset values")
        ],
        default='DEFAULT',
        update=update_julibrot
    )
    scale_x: FloatProperty(
        name="Scale X", default=1.5, update=update_julibrot
    )
    scale_y: FloatProperty(
        name="Scale Y", default=1.5, update=update_julibrot
    )
    offset_x: FloatProperty(
        name="Offset X", default=-0.5, update=update_julibrot
    )
    z_height_start: FloatProperty(
        name="Z Height Start",
        description="Initial Z search depth",
        default=1.5, min=0.0,
        update=update_julibrot
    )
    step_size: FloatProperty(
        name="Step Size",
        description="Z-ray step resolution",
        default=0.05, min=0.001, max=0.5, precision=3,
        update=update_julibrot
    )
    auto_update: BoolProperty(
        name="Auto Update",
        description="Regenerate geometry automatically on property edit",
        default=False
    )


# --- OPERATOR ---

class OBJECT_OT_generate_julibrot(bpy.types.Operator):
    bl_idname = "object.generate_julibrot"
    bl_label = "Generate Object"
    bl_description = "Generate or rebuild the Julibrot object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        build_julibrot_planet(context)
        return {'FINISHED'}


# --- N-PANEL INTERFACE ---

class VIEW3D_PT_julibrot_panel(bpy.types.Panel):
    bl_label = "Julibrot Generator"
    bl_idname = "VIEW3D_PT_julibrot_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Julibrot'

    def draw(self, context):
        layout = self.layout
        props = context.scene.julibrot_props

        # Base Geometry Controls
        box = layout.box()
        box.label(text="Base Geometry", icon='MESH_DATA')
        box.prop(props, "base_shape")
        if props.base_shape == 'TORUS':
            box.prop(props, "torus_minor")
        box.prop(props, "resolution")
        box.prop(props, "base_radius")
        box.prop(props, "frac_strength")
        box.prop(props, "max_iter")

        # Complex Plane Structure Controls
        box = layout.box()
        box.label(text="Structure Mapping", icon='PROPERTIES')
        box.prop(props, "mapping_preset")
        if props.mapping_preset == 'CUSTOM':
            col = box.column(align=True)
            col.prop(props, "scale_x")
            col.prop(props, "scale_y")
            col.prop(props, "offset_x")

        # Ray Marching Depth Controls
        box = layout.box()
        box.label(text="Ray Marching Settings", icon='MODIFIER')
        box.prop(props, "z_height_start")
        box.prop(props, "step_size")

        # Action Buttons
        layout.separator()
        layout.prop(props, "auto_update", toggle=True, icon='FILE_REFRESH')
        layout.operator("object.generate_julibrot", icon='FILE_REFRESH')


# --- REGISTRATION ---

classes = (
    JulibrotProperties,
    OBJECT_OT_generate_julibrot,
    VIEW3D_PT_julibrot_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.julibrot_props = PointerProperty(type=JulibrotProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, "julibrot_props"):
        del bpy.types.Scene.julibrot_props

if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()