bl_info = {
    "name": "First Scherk Surface",
    "author": "smice",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Add > Mesh > Scherk",
    "description": "Adds a Scherk's second minimal surface (Scherk-Collins)",
    "warning": "",
    "doc_url": "https://mathcurve.com/surfaces.gb/scherk/scherk.shtml",
    "category": "Add Mesh",
}

import bpy
import bmesh
import math
from bpy.props import IntProperty, FloatProperty

class OBJECT_OT_add_scherk_first_surface(bpy.types.Operator):
    """Add a tiled Scherk's minimal surface"""
    bl_idname = "mesh.primitive_scherk_first_add"
    bl_label = "Scherk Surface"
    bl_options = {'REGISTER', 'UNDO'}

    x_tiles: IntProperty(
        name="X Tiles",
        description="Number of tiles in the X-direction",
        default=2,
        min=1,
        max=100,
    )
    y_tiles: IntProperty(
        name="Y Tiles",
        description="Number of tiles in the Y-direction",
        default=2,
        min=1,
        max=100,
    )
    resolution: IntProperty(
        name="Tile Resolution",
        description="Number of steps per tile",
        default=40,
        min=2,
        max=1024,
    )
    range: FloatProperty(
        name="Tile Range (near pi/2)",
        description="Parameter range for each tile. 1.57 (pi/2) is the max",
        default=1.55,
        min=0.1,
        max=1.5707, # Just over pi/2
    )
    scale: FloatProperty(
        name="Scale",
        description="Overall scale of the mesh",
        default=1.0,
        min=0.01,
        max=100.0,
    )

    def execute(self, context):
        verts = []
        faces = []
        
        tile_width = self.range * 2
        total_x_steps = self.resolution * self.x_tiles
        total_y_steps = self.resolution * self.y_tiles
        
        # Total size of the mesh for centering
        total_width = self.x_tiles * tile_width
        total_height = self.y_tiles * tile_width
        
        center_offset_x = total_width / 2.0
        center_offset_y = total_height / 2.0
        
        verts_per_row = total_y_steps + 1

        # --- Calculate Vertices ---
        # Loop through the total number of vertices needed
        for i in range(total_x_steps + 1):
            # Calculate current X tile and position within that tile
            tile_i = min(i // self.resolution, self.x_tiles - 1)
            i_in_tile = i % self.resolution
            # Handle the last vertex column
            if i == total_x_steps:
                i_in_tile = self.resolution
            
            # u_param is the parameter for cos(x), from -range to +range
            u_norm = (i_in_tile / self.resolution) * 2.0 - 1.0
            u_param = u_norm * self.range
            
            # x is the actual world coordinate, from 0 to total_width
            x = (i / total_x_steps) * total_width - center_offset_x
            
            for j in range(total_y_steps + 1):
                # Calculate current Y tile and position within that tile
                tile_j = min(j // self.resolution, self.y_tiles - 1)
                j_in_tile = j % self.resolution
                # Handle the last vertex row
                if j == total_y_steps:
                    j_in_tile = self.resolution
                    
                # v_param is the parameter for cos(y), from -range to +range
                v_norm = (j_in_tile / self.resolution) * 2.0 - 1.0
                v_param = v_norm * self.range
                
                # y is the actual world coordinate, from 0 to total_height
                y = (j / total_y_steps) * total_height - center_offset_y
                
                # Check if the tile should be flipped
                is_flipped = (tile_i + tile_j) % 2 == 1
                
                # Equation: z = log(cos(v) / cos(u))
                cos_x = math.cos(u_param)
                cos_y = math.cos(v_param)
                
                z = 0.0
                # Avoid division by zero at the "holes" (where cos(u) is 0)
                if cos_x > 1e-6:
                    z = math.log(cos_y / cos_x)
                
                # Flip every other tile
                if is_flipped:
                    z = -z

                verts.append((x * self.scale, y * self.scale, z * self.scale))

        # --- Create Faces ---
        # Loop through the total number of quads
        for i in range(total_x_steps):
            for j in range(total_y_steps):
                # Calculate indices for the four vertices of a quad
                v1 = i * verts_per_row + j
                v2 = i * verts_per_row + (j + 1)
                v3 = (i + 1) * verts_per_row + (j + 1)
                v4 = (i + 1) * verts_per_row + j
                
                faces.append((v1, v2, v3, v4))

        # --- Create Mesh and Object ---
        
        mesh = bpy.data.meshes.new(name="ScherkFirstSurface")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new("ScherkFirstSurface", mesh)
        context.collection.objects.link(obj)
        context.view_layer.objects.active = obj
        obj.select_set(True)

        return {'FINISHED'}


# --- Registration ---

def menu_func(self, context):
    self.layout.operator(OBJECT_OT_add_scherk_first_surface.bl_idname, icon='MESH_GRID')

def register():
    bpy.utils.register_class(OBJECT_OT_add_scherk_first_surface)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)

def unregister():
    bpy.utils.register_class(OBJECT_OT_add_scherk_first_surface)
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)

# This allows the script to be run directly in Blender's Text Editor
if __name__ == "__main__":
    # Unregister the old one if it's still running
    try:
        # This will try to unregister the class from the *previous* version
        # of the script, using its bl_idname.
        bpy.utils.unregister_class(bpy.types.OBJECT_OT_add_scherk_first_surface)
        bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    except:
        pass
    
    # Unregister the very first version (Scherk Second) just in case
    try:
        bpy.utils.unregister_class(bpy.types.OBJECT_OT_add_scherk_second_add)
        bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    except:
        pass
    
    register()
