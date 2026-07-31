import bpy
import math
import cmath

# --- SETTINGS ---
N = 9           # Heptagons (Use 5 or 6 for simpler forms, 7 or 8 for complexity)
M = 3           # 3 meet at each vertex
ITERATIONS = 6  # Fractal depth (4 is maximum safe depth for memory)
SCALE = 2.0
THICKNESS = 0.004 # Wire thickness

# --- Hyperbolic Math Helpers ---
def homography(mat, z):
    a, b = mat[0]
    c, d = mat[1]
    denom = c * z + d
    if abs(denom) < 1e-12: return complex(0,0)
    return (a * z + b) / denom

def mat_mul(m1, m2):
    return [
        [m1[0][0]*m2[0][0] + m1[0][1]*m2[1][0], m1[0][0]*m2[0][1] + m1[0][1]*m2[1][1]],
        [m1[1][0]*m2[0][0] + m1[1][1]*m2[1][0], m1[1][0]*m2[0][1] + m1[1][1]*m2[1][1]]
    ]

# --- 2D Poincaré Disk Generator ---
dt = 2 * math.pi / N
dtm = 2 * math.pi / M
r_val = 1.0 / (1.0 - math.sin(dt/2.0) / math.cos(dtm/2.0))
R_poly = r_val * math.cos((dt + dtm)/2.0) / math.cos(dtm/2.0)

def to_matrix(z, r):
    r_sq_abs_z = r**2 - (z.real**2 + z.imag**2)
    return [
        [complex(0, z.real/r), complex(0, r_sq_abs_z/r)],
        [complex(0, 1/r), complex(0, -z.conjugate().real/r)]
    ]

# --- Execution ---
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 1. Generate the Transformations (Identical to 2D)
alist = [to_matrix(cmath.exp(complex(0, i * dt + dt/2)) * r_val, r_val - 1) for i in range(N)]
t_list = [[[complex(1,0), complex(0,0)], [complex(0,0), complex(1,0)]]] # Identity

curr_idx = 0
for _ in range(ITERATIONS):
    next_idx = len(t_list)
    for i in range(curr_idx, next_idx):
        for a in alist:
            new_t = mat_mul(t_list[i], a)
            z_center = homography(new_t, 0)
            exists = False
            for existing_t in t_list:
                if abs(homography(existing_t, 0) - z_center) < 1e-3:
                    exists = True
                    break
            if not exists:
                t_list.append(new_t)
    curr_idx = next_idx

# 2. Convert to 3D Sphere in Blender (Stereographic Projection)
curve_data = bpy.data.curves.new('HyperbolicPlanet', type='CURVE')
curve_data.dimensions = '3D'
curve_data.fill_mode = 'FULL'
curve_data.bevel_depth = THICKNESS

print(f"Generating {len(t_list)} Hyperbolic Heptagons on Sphere...")

for t_mat in t_list:
    polyline = curve_data.splines.new('POLY')
    points = []
    
    # We use high resolution for the heptagon edges because they curve wildly
    resolution = 12 
    for i in range(N):
        for step in range(resolution + 1):
            angle = (i + step / resolution) * dt
            z_point = R_poly * cmath.exp(complex(0, angle))
            # Poincaré Disk (2D)
            z_flat = homography(t_mat, z_point) 
            
            # --- STEREOGRAPHIC SPHERE PROJECTION ---
            # Inverse of (z.x / (1+z.z), z.y / (1+z.z))
            # maps the flat disk complex plane onto a 3D sphere
            
            x, y = z_flat.real, z_flat.imag
            norm_sq = x*x + y*y
            if norm_sq < 1e-12: norm_sq = 1e-12
            
            # The denominator (1 + norm_sq) prevents singularity at infinity
            denom = 1.0 + norm_sq
            
            # Formula: (2x/denom, 2y/denom, (norm_sq-1)/denom)
            # North Pole is +Z, South Pole is -Z
            px = 2.0 * x / denom
            py = 2.0 * y / denom
            pz = (norm_sq - 1.0) / denom
            
            points.append((px * SCALE, py * SCALE, pz * SCALE))
    
    polyline.points.add(len(points) - 1)
    for i, pt in enumerate(points):
        polyline.points[i].co = (pt[0], pt[1], pt[2], 1)

obj = bpy.data.objects.new('HyperbolicPlanet', curve_data)
bpy.context.collection.objects.link(obj)

# 3. Visuals: Obsidian Chrome
mat = bpy.data.materials.new(name="ObsidianChrome")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs['Base Color'].default_value = (0.01, 0.01, 0.02, 1.0)
bsdf.inputs['Metallic'].default_value = 1.0
bsdf.inputs['Roughness'].default_value = 0.08
obj.data.materials.append(mat)

# ADD A BASE SPHERE (The Planet's Surface)
bpy.ops.mesh.primitive_uv_sphere_add(radius=SCALE * 0.99, location=(0,0,0))
planet_base = bpy.context.active_object
planet_base.name = "PlanetSurface"
bpy.ops.object.shade_smooth()
mat_base = bpy.data.materials.new(name="DeepSpace")
mat_base.use_nodes = True
bsdf_base = mat_base.node_tree.nodes.get("Principled BSDF")
bsdf_base.inputs['Base Color'].default_value = (0.05, 0.02, 0.1, 1.0)
planet_base.data.materials.append(mat_base)

print("Hyperbolic Planet V2 (Sphere) is Complete.")