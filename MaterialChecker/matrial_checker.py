# Blender script: Image-chooser for material Image Texture node
# with pagination (100 per page), 3 columns, large thumbnails (scale=7)
# Paste into Blender Text Editor and Run Script (or install as an add-on).
# Author: ChatGPT (example)

import bpy
import os
import math
import bpy.utils.previews

# ----------------- Configuration -----------------
IMAGE_DIR = bpy.path.abspath("//")   # default = folder with .blend
THUMB_EXTS = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".exr", ".hdr"}
THUMB_COLUMNS = 3                    # thumbnails per row (user said keep 3)
THUMB_SCALE = 7                      # thumbnail scale (1..10+). you liked 7
PAGE_SIZE = 100                      # number of thumbnails per page
# -------------------------------------------------

PREVIEWS = None
IMAGE_FILES = []  # list of (filename, filepath)

def find_image_files(path):
    files = []
    if not os.path.isdir(path):
        return files
    for f in sorted(os.listdir(path)):
        # Skip hidden/system files starting with '.'
        if f.startswith('.'):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in THUMB_EXTS:
            files.append((f, os.path.join(path, f)))
    return files

def ensure_previews():
    """Create previews collection and load previews for all image files found."""
    global PREVIEWS, IMAGE_FILES
    if PREVIEWS is None:
        PREVIEWS = bpy.utils.previews.new()
    # re-scan image files if needed
    if not IMAGE_FILES:
        IMAGE_FILES = find_image_files(IMAGE_DIR)
    # load previews for all files (fast enough for a few hundred)
    for fname, fpath in IMAGE_FILES:
        if PREVIEWS.get(fname) is None:
            try:
                PREVIEWS.load(fname, fpath, 'IMAGE')
            except Exception as e:
                print("Preview load failed for", fpath, e)
    return PREVIEWS

def clear_previews():
    global PREVIEWS
    if PREVIEWS is not None:
        bpy.utils.previews.remove(PREVIEWS)
        PREVIEWS = None

def get_page_info():
    """Return (page_index, page_count) where page_index is 0-based."""
    total = len(IMAGE_FILES)
    page_count = max(1, math.ceil(total / PAGE_SIZE))
    page_index = max(0, min(bpy.context.scene.image_browser_page, page_count - 1))
    return page_index, page_count

# Operator: set material image node to the chosen image
class WM_OT_set_material_image(bpy.types.Operator):
    bl_idname = "wm.set_material_image"
    bl_label = "Set Material Image"
    filepath: bpy.props.StringProperty()
    filename: bpy.props.StringProperty()

    def execute(self, context):
        filepath = self.filepath
        fname = self.filename

        obj = context.active_object
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}

        mat = obj.active_material if obj.active_material else (obj.material_slots[0].material if obj.material_slots else None)
        if mat is None:
            self.report({'ERROR'}, "Active object has no material")
            return {'CANCELLED'}

        if not mat.use_nodes:
            self.report({'ERROR'}, "Material has no node tree (enable Use Nodes)")
            return {'CANCELLED'}

        img_node = None
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                img_node = node
                break
        if img_node is None:
            self.report({'ERROR'}, "No Image Texture node found in material")
            return {'CANCELLED'}

        # Load or reuse the image in bpy.data.images
        img = bpy.data.images.get(fname)
        if img is None:
            try:
                img = bpy.data.images.load(filepath, check_existing=True)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to load image: {e}")
                return {'CANCELLED'}

        img_node.image = img

        # ensure viewport updates
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        self.report({'INFO'}, f"Assigned image '{fname}' to material '{mat.name}'")
        return {'FINISHED'}

# Pagination operators
class WM_OT_next_page(bpy.types.Operator):
    bl_idname = "wm.image_browser_next_page"
    bl_label = "Next Image Page"

    def execute(self, context):
        page_idx, page_count = get_page_info()
        if page_idx < page_count - 1:
            context.scene.image_browser_page = page_idx + 1
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
        return {'FINISHED'}

class WM_OT_prev_page(bpy.types.Operator):
    bl_idname = "wm.image_browser_prev_page"
    bl_label = "Previous Image Page"

    def execute(self, context):
        page_idx, page_count = get_page_info()
        if page_idx > 0:
            context.scene.image_browser_page = page_idx - 1
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
        return {'FINISHED'}

# Refresh operator (re-scan folder and reset to page 0)
class WM_OT_refresh_image_previews(bpy.types.Operator):
    bl_idname = "wm.refresh_image_previews"
    bl_label = "Refresh Image Previews"

    def execute(self, context):
        global IMAGE_FILES
        clear_previews()
        IMAGE_FILES = find_image_files(IMAGE_DIR)
        ensure_previews()
        context.scene.image_browser_page = 0
        self.report({'INFO'}, f"Found {len(IMAGE_FILES)} images in {IMAGE_DIR}")
        return {'FINISHED'}

# Panel: show thumbnails and allow clicking, with pagination
class MATERIAL_PT_image_browser(bpy.types.Panel):
    bl_label = "Image Browser (folder)"
    bl_idname = "MATERIAL_PT_image_browser"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and (context.active_object.active_material is not None or len(context.active_object.material_slots) > 0)

    def draw(self, context):
        layout = self.layout
        ensure_previews()

        if not IMAGE_FILES:
            layout.label(text=f"No images in: {IMAGE_DIR}")
            layout.operator("wm.refresh_image_previews", text="Refresh (re-scan folder)")
            return

        page_idx, page_count = get_page_info()
        start = page_idx * PAGE_SIZE
        end = start + PAGE_SIZE
        page_items = IMAGE_FILES[start:end]

        # header with Prev / Page X / Next and refresh button
        row = layout.row(align=True)
        row.operator("wm.image_browser_prev_page", text="", icon='TRIA_LEFT')
        row.label(text=f"Page {page_idx + 1} / {page_count}")
        row.operator("wm.image_browser_next_page", text="", icon='TRIA_RIGHT')
        row.separator()
        row.operator("wm.refresh_image_previews", text="", icon='FILE_REFRESH')

        # grid flow for thumbnails
        flow = layout.grid_flow(row_major=True, columns=THUMB_COLUMNS, even_columns=True, even_rows=True)
        for fname, fpath in page_items:
            icon = PREVIEWS.get(fname)
            # Make icon button larger using template_icon with scale
            col = flow.column()
            if icon:
                op = col.operator("wm.set_material_image", text="", icon='EYEDROPPER')
                #op = col.operator("wm.set_material_image", text="")
                op.filepath = fpath
                op.filename = fname
                # show thumbnail with chosen scale
                col.template_icon(icon_value=icon.icon_id, scale=THUMB_SCALE)
            else:
                # fallback: simple text button
                op = col.operator("wm.set_material_image", text=fname)
                op.filepath = fpath
                op.filename = fname

        layout.separator()
        layout.label(text=f"Showing {len(page_items)} of {len(IMAGE_FILES)} images (folder: {os.path.basename(IMAGE_DIR)})")

# register/unregister
classes = (
    WM_OT_set_material_image,
    WM_OT_next_page,
    WM_OT_prev_page,
    WM_OT_refresh_image_previews,
    MATERIAL_PT_image_browser,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    # scene property to hold current page index
    bpy.types.Scene.image_browser_page = bpy.props.IntProperty(name="Image Browser Page", default=0, min=0)
    # load initial list and previews
    global IMAGE_FILES
    IMAGE_FILES = find_image_files(IMAGE_DIR)
    ensure_previews()
    print("Image chooser (paged) registered. Scanned:", IMAGE_DIR)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    try:
        del bpy.types.Scene.image_browser_page
    except Exception:
        pass
    clear_previews()
    print("Image chooser (paged) unregistered.")

if __name__ == "__main__":
    register()
