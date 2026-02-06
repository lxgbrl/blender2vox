"""
Voxelization and Export Logic for Blender to VOX

This module handles:
1. Detecting if mesh was imported from VOX (preserves exact voxel data)
2. Extracting mesh geometry from Blender objects
3. Voxelizing the mesh using ray casting
4. Extracting colors from vertex colors or materials
5. Building color palette
6. Exporting to VOX format
"""

import bpy
import bmesh
import mathutils
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from typing import List, Tuple, Dict, Optional, Set
import math
from collections import defaultdict
import json

from . import vox_writer
from . import vox_importer


def color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Calculate Euclidean distance between two RGB colors."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def quantize_colors(colors: List[Tuple[int, int, int]], max_colors: int = 255) -> Tuple[List[Tuple[int, int, int]], Dict[Tuple[int, int, int], int]]:
    """Quantize colors to fit within max_colors using median cut algorithm.

    Returns:
        Tuple of (palette list, color to index mapping)
    """
    if not colors:
        # Return a default palette with visible gray
        return [(180, 180, 180)], {(180, 180, 180): 1}

    unique_colors = list(set(colors))

    if len(unique_colors) <= max_colors:
        # No quantization needed
        palette = unique_colors
        color_to_index = {c: i + 1 for i, c in enumerate(palette)}
        return palette, color_to_index

    # Simple median cut implementation
    def median_cut(box: List[Tuple[int, int, int]], depth: int) -> List[Tuple[int, int, int]]:
        if depth == 0 or len(box) <= 1:
            # Return average color
            if not box:
                return [(180, 180, 180)]
            r = sum(c[0] for c in box) // len(box)
            g = sum(c[1] for c in box) // len(box)
            b = sum(c[2] for c in box) // len(box)
            return [(r, g, b)]

        # Find dimension with largest range
        r_range = max(c[0] for c in box) - min(c[0] for c in box)
        g_range = max(c[1] for c in box) - min(c[1] for c in box)
        b_range = max(c[2] for c in box) - min(c[2] for c in box)

        if r_range >= g_range and r_range >= b_range:
            sort_key = lambda c: c[0]
        elif g_range >= b_range:
            sort_key = lambda c: c[1]
        else:
            sort_key = lambda c: c[2]

        sorted_box = sorted(box, key=sort_key)
        mid = len(sorted_box) // 2

        return median_cut(sorted_box[:mid], depth - 1) + median_cut(sorted_box[mid:], depth - 1)

    # Calculate depth needed
    depth = int(math.log2(max_colors))
    palette = median_cut(unique_colors, depth)

    # Ensure we don't exceed max_colors
    palette = palette[:max_colors]

    # Build mapping from original colors to palette indices
    color_to_index = {}
    for color in unique_colors:
        # Find closest palette color
        best_idx = 0
        best_dist = float('inf')
        for i, pc in enumerate(palette):
            dist = color_distance(color, pc)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        color_to_index[color] = best_idx + 1  # VOX uses 1-based indexing

    return palette, color_to_index


class VoxExporter:
    """Main exporter class for converting Blender objects to VOX format."""

    # Default color for objects without any color data (visible light gray)
    DEFAULT_COLOR = (180, 180, 180)

    def __init__(self,
                 voxel_size: float = 0.1,
                 max_size: int = 126,
                 use_vertex_colors: bool = True,
                 use_material_colors: bool = True,
                 center_model: bool = True,
                 apply_transforms: bool = True,
                 fill_interior: bool = False,
                 ray_samples: int = 3,
                 palette_mode: str = 'QUANTIZE',
                 preserve_vox_data: bool = True):
        self.voxel_size = voxel_size
        self.max_size = min(max_size, 256)
        self.use_vertex_colors = use_vertex_colors
        self.use_material_colors = use_material_colors
        self.center_model = center_model
        self.apply_transforms = apply_transforms
        self.fill_interior = fill_interior
        self.ray_samples = ray_samples
        self.palette_mode = palette_mode
        self.preserve_vox_data = preserve_vox_data

    def export(self, objects: List[bpy.types.Object], filepath: str):
        """Export objects to VOX file."""
        all_voxels = []  # Will contain (x, y, z, color_idx) for preserved, (x, y, z, (r,g,b)) for voxelized
        original_palette = None
        use_original_indices = False

        for obj in objects:
            # Check if this object has VOX metadata (was imported from VOX)
            if self.preserve_vox_data:
                metadata = vox_importer.get_vox_metadata(obj)
                if metadata and 'voxels' in metadata and metadata.get('palette'):
                    print(f"Using preserved VOX data for {obj.name}")
                    # Use original voxel data with ORIGINAL color indices
                    for voxel in metadata['voxels']:
                        x, y, z, color_idx = voxel
                        all_voxels.append((x, y, z, color_idx))

                    original_palette = metadata['palette']
                    use_original_indices = True
                    continue

            # No VOX metadata, voxelize the mesh
            voxels = self._voxelize_object(obj)
            all_voxels.extend(voxels)

        if not all_voxels:
            raise ValueError("No voxels generated from objects")

        # Calculate bounding box
        min_x = min(v[0] for v in all_voxels)
        min_y = min(v[1] for v in all_voxels)
        min_z = min(v[2] for v in all_voxels)
        max_x = max(v[0] for v in all_voxels)
        max_y = max(v[1] for v in all_voxels)
        max_z = max(v[2] for v in all_voxels)

        # Calculate actual model size
        size_x = max_x - min_x + 1
        size_y = max_y - min_y + 1
        size_z = max_z - min_z + 1

        # Create VOX file
        writer = vox_writer.VoxWriter()
        model = vox_writer.VoxModel(size_x, size_y, size_z)

        if use_original_indices and original_palette:
            # Use original palette and color indices exactly
            print("Using original palette and color indices")

            # Set the original palette
            for i, (r, g, b, a) in enumerate(original_palette):
                if i < 255:  # VOX palette has 255 usable colors (1-255)
                    writer.palette.set_color(i + 1, r, g, b, a)

            # Add voxels with original color indices, normalizing coordinates
            seen = set()
            for x, y, z, color_idx in all_voxels:
                nx = x - min_x
                ny = y - min_y
                nz = z - min_z

                # Clamp coordinates
                nx = max(0, min(255, nx))
                ny = max(0, min(255, ny))
                nz = max(0, min(255, nz))

                key = (nx, ny, nz)
                if key not in seen:
                    seen.add(key)
                    # Ensure color index is valid (1-255)
                    if 1 <= color_idx <= 255:
                        model.add_voxel(nx, ny, nz, color_idx)
                    else:
                        model.add_voxel(nx, ny, nz, 1)  # Default to first color

            writer.add_model(model)
            writer.write(filepath)

            print(f"Exported {len(seen)} voxels to {filepath}")
            print(f"Model size: {size_x} x {size_y} x {size_z}")
            return

        # Standard export path: normalize and quantize colors
        normalized_voxels = []
        for x, y, z, color in all_voxels:
            nx = x - min_x
            ny = y - min_y
            nz = z - min_z

            # Clamp to valid range
            nx = max(0, min(255, nx))
            ny = max(0, min(255, ny))
            nz = max(0, min(255, nz))

            normalized_voxels.append((nx, ny, nz, color))

        # Remove duplicates (keep first occurrence)
        seen = set()
        unique_voxels = []
        for voxel in normalized_voxels:
            key = (voxel[0], voxel[1], voxel[2])
            if key not in seen:
                seen.add(key)
                unique_voxels.append(voxel)

        # Quantize colors
        colors = [v[3] for v in unique_voxels]

        # Debug: show unique colors found
        unique_colors_set = set(colors)
        print(f"[DEBUG] Unique colors in voxels: {unique_colors_set}")

        palette, color_map = quantize_colors(colors, 255)
        print(f"[DEBUG] Palette: {palette[:10]}...")  # First 10

        # Set palette colors
        for i, (r, g, b) in enumerate(palette):
            writer.palette.set_color(i + 1, r, g, b, 255)

        # Add voxels
        for x, y, z, color in unique_voxels:
            color_index = color_map.get(color, 1)
            model.add_voxel(x, y, z, color_index)

        writer.add_model(model)
        writer.write(filepath)

        print(f"Exported {len(unique_voxels)} voxels to {filepath}")
        print(f"Model size: {size_x} x {size_y} x {size_z}")
        print(f"Palette colors: {len(palette)}")

    def _voxelize_object(self, obj: bpy.types.Object) -> List[Tuple[int, int, int, Tuple[int, int, int]]]:
        """Voxelize a single Blender object.

        Returns:
            List of (x, y, z, (r, g, b)) tuples
        """
        # Get mesh data
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        # Apply world transform if requested
        if self.apply_transforms:
            mesh.transform(obj.matrix_world)

        # Get color data BEFORE triangulation (from original mesh)
        # We need to map original polygon -> color
        original_colors = self._extract_colors(mesh, obj)

        # Create BVH tree for ray casting
        bm = bmesh.new()
        bm.from_mesh(mesh)

        # Store original face index before triangulation
        # Create a custom layer to track which original polygon each triangle came from
        orig_face_layer = bm.faces.layers.int.new('orig_face')
        for face in bm.faces:
            face[orig_face_layer] = face.index

        # Triangulate - this creates new faces but preserves the layer data
        bmesh.ops.triangulate(bm, faces=bm.faces)

        # Build mapping from triangulated face index to original face index
        bm.faces.ensure_lookup_table()
        tri_to_orig = {}
        for i, face in enumerate(bm.faces):
            tri_to_orig[i] = face[orig_face_layer]

        bvh = BVHTree.FromBMesh(bm)

        # Build color_data with triangulated face mapping
        color_data = {
            'tri_to_orig': tri_to_orig,
            'vertex_colors': original_colors['vertex_colors'],
            'material_colors': original_colors['material_colors'],
            'face_materials': original_colors['face_materials'],
            'default_color': original_colors['default_color'],
        }

        # Calculate bounding box
        bbox_min = Vector((float('inf'), float('inf'), float('inf')))
        bbox_max = Vector((float('-inf'), float('-inf'), float('-inf')))

        for v in mesh.vertices:
            co = v.co
            bbox_min.x = min(bbox_min.x, co.x)
            bbox_min.y = min(bbox_min.y, co.y)
            bbox_min.z = min(bbox_min.z, co.z)
            bbox_max.x = max(bbox_max.x, co.x)
            bbox_max.y = max(bbox_max.y, co.y)
            bbox_max.z = max(bbox_max.z, co.z)

        # Calculate grid dimensions
        size = bbox_max - bbox_min
        grid_x = int(math.ceil(size.x / self.voxel_size)) + 1
        grid_y = int(math.ceil(size.y / self.voxel_size)) + 1
        grid_z = int(math.ceil(size.z / self.voxel_size)) + 1

        # Limit to max_size
        scale_factor = 1.0
        max_dim = max(grid_x, grid_y, grid_z)
        if max_dim > self.max_size:
            scale_factor = self.max_size / max_dim
            grid_x = int(grid_x * scale_factor)
            grid_y = int(grid_y * scale_factor)
            grid_z = int(grid_z * scale_factor)

        adjusted_voxel_size = self.voxel_size / scale_factor

        voxels = []

        # Voxelize using ray casting
        for gx in range(grid_x):
            for gy in range(grid_y):
                for gz in range(grid_z):
                    # Calculate world position of voxel center
                    world_pos = Vector((
                        bbox_min.x + (gx + 0.5) * adjusted_voxel_size,
                        bbox_min.y + (gy + 0.5) * adjusted_voxel_size,
                        bbox_min.z + (gz + 0.5) * adjusted_voxel_size,
                    ))

                    # Check if this voxel should be filled
                    is_filled, color = self._check_voxel(
                        bvh, world_pos, adjusted_voxel_size, color_data
                    )

                    if is_filled:
                        voxels.append((gx, gy, gz, color))

        # Clean up
        bm.free()
        obj_eval.to_mesh_clear()

        return voxels

    def _extract_colors(self, mesh: bpy.types.Mesh, obj: bpy.types.Object) -> Dict:
        """Extract color information from mesh.

        Returns dictionary with color data that can be queried by face index or UV.
        """
        color_data = {
            'vertex_colors': None,
            'material_colors': {},
            'face_materials': [],
            'default_color': self.DEFAULT_COLOR,
            'has_any_color': False,
        }

        print(f"[DEBUG] Extracting colors from {obj.name}")
        print(f"[DEBUG] Material slots: {len(obj.material_slots)}")
        print(f"[DEBUG] Mesh polygons: {len(mesh.polygons)}")

        # Extract vertex colors (check both old and new API)
        if self.use_vertex_colors:
            color_layer = None

            # Try new API first (Blender 3.2+)
            if hasattr(mesh, 'color_attributes') and mesh.color_attributes:
                color_layer = mesh.color_attributes.active_color
                print(f"[DEBUG] Using color_attributes API, layer: {color_layer.name if color_layer else 'None'}")
            # Fall back to old API
            elif hasattr(mesh, 'vertex_colors') and mesh.vertex_colors:
                color_layer = mesh.vertex_colors.active
                print(f"[DEBUG] Using vertex_colors API, layer: {color_layer.name if color_layer else 'None'}")
            else:
                print(f"[DEBUG] No vertex colors found")

            if color_layer:
                color_data['vertex_colors'] = {}
                color_data['has_any_color'] = True
                for poly in mesh.polygons:
                    face_colors = []
                    for loop_idx in poly.loop_indices:
                        col = color_layer.data[loop_idx].color
                        r = int(col[0] * 255)
                        g = int(col[1] * 255)
                        b = int(col[2] * 255)
                        face_colors.append((r, g, b))
                    color_data['vertex_colors'][poly.index] = face_colors
                # Debug: show first face color
                if color_data['vertex_colors']:
                    first_colors = list(color_data['vertex_colors'].values())[0]
                    print(f"[DEBUG] First face vertex colors: {first_colors}")

        # Extract material colors
        if self.use_material_colors:
            for i, mat_slot in enumerate(obj.material_slots):
                mat = mat_slot.material
                if mat:
                    # Try to get base color from principled BSDF
                    color = self._get_material_color(mat)
                    color_data['material_colors'][i] = color
                    color_data['has_any_color'] = True
                    print(f"[DEBUG] Material {i} '{mat.name}': RGB{color}")
                else:
                    print(f"[DEBUG] Material slot {i}: no material assigned")

        # Store face material indices
        for poly in mesh.polygons:
            color_data['face_materials'].append(poly.material_index)

        print(f"[DEBUG] Face material indices: {color_data['face_materials'][:10]}...")  # First 10
        print(f"[DEBUG] has_any_color: {color_data['has_any_color']}")

        return color_data

    def _get_material_color(self, material: bpy.types.Material) -> Tuple[int, int, int]:
        """Extract base color from a material."""
        if material.use_nodes:
            # Find Principled BSDF node
            for node in material.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    base_color = node.inputs['Base Color'].default_value
                    r = int(base_color[0] * 255)
                    g = int(base_color[1] * 255)
                    b = int(base_color[2] * 255)
                    return (r, g, b)

        # Fallback to diffuse color
        col = material.diffuse_color
        r = int(col[0] * 255)
        g = int(col[1] * 255)
        b = int(col[2] * 255)
        return (r, g, b)

    def _check_voxel(self, bvh: BVHTree, pos: Vector, voxel_size: float,
                     color_data: Dict) -> Tuple[bool, Tuple[int, int, int]]:
        """Check if a voxel position should be filled and get its color.

        Uses ray casting to determine if the voxel intersects with the mesh surface.
        """
        # Cast rays in multiple directions to detect surface
        directions = [
            Vector((1, 0, 0)), Vector((-1, 0, 0)),
            Vector((0, 1, 0)), Vector((0, -1, 0)),
            Vector((0, 0, 1)), Vector((0, 0, -1)),
        ]

        # Add diagonal directions for better coverage
        if self.ray_samples >= 2:
            diag = 1.0 / math.sqrt(3)
            directions.extend([
                Vector((diag, diag, diag)), Vector((-diag, -diag, -diag)),
                Vector((diag, -diag, diag)), Vector((-diag, diag, -diag)),
            ])

        hit_face = None
        min_dist = float('inf')

        for direction in directions:
            # Cast ray from outside the voxel
            ray_origin = pos - direction * voxel_size * 2

            result = bvh.ray_cast(ray_origin, direction)
            if result[0] is not None:
                hit_pos, normal, face_idx, dist = result

                # Check if hit is within or near the voxel
                to_hit = hit_pos - pos
                if abs(to_hit.x) <= voxel_size and abs(to_hit.y) <= voxel_size and abs(to_hit.z) <= voxel_size:
                    if dist < min_dist:
                        min_dist = dist
                        hit_face = face_idx

        if hit_face is None:
            # Check for interior fill
            if self.fill_interior:
                # Count ray intersections (odd = inside)
                inside_count = 0
                for direction in directions[:6]:
                    result = bvh.ray_cast(pos, direction)
                    if result[0] is not None:
                        inside_count += 1

                if inside_count == 6:  # Rays hit in all directions = inside
                    return True, color_data['default_color']

            return False, (0, 0, 0)

        # Get color for the hit face
        color = self._get_face_color(hit_face, color_data)
        return True, color

    def _get_face_color(self, face_idx: int, color_data: Dict) -> Tuple[int, int, int]:
        """Get the color for a face.

        Args:
            face_idx: The triangulated face index from BVH ray cast
            color_data: Color data dict containing tri_to_orig mapping
        """
        # Map triangulated face index back to original polygon index
        orig_face_idx = face_idx
        if 'tri_to_orig' in color_data and face_idx in color_data['tri_to_orig']:
            orig_face_idx = color_data['tri_to_orig'][face_idx]

        # Try vertex colors first (using original polygon index)
        if color_data['vertex_colors'] and orig_face_idx in color_data['vertex_colors']:
            colors = color_data['vertex_colors'][orig_face_idx]
            if colors:
                # Average vertex colors for the face
                r = sum(c[0] for c in colors) // len(colors)
                g = sum(c[1] for c in colors) // len(colors)
                b = sum(c[2] for c in colors) // len(colors)
                return (r, g, b)

        # Try material color (using original polygon index)
        if orig_face_idx < len(color_data['face_materials']):
            mat_idx = color_data['face_materials'][orig_face_idx]
            if mat_idx in color_data['material_colors']:
                return color_data['material_colors'][mat_idx]

        # Default color (visible gray, not black)
        return color_data['default_color']


# Utility functions for use outside of Blender

def voxelize_from_vertices(vertices: List[Tuple[float, float, float]],
                           faces: List[Tuple[int, ...]],
                           colors: Optional[List[Tuple[int, int, int]]] = None,
                           voxel_size: float = 0.1) -> List[Tuple[int, int, int, Tuple[int, int, int]]]:
    """Voxelize geometry from raw vertex/face data.

    Args:
        vertices: List of (x, y, z) vertex positions
        faces: List of face vertex indices
        colors: Optional list of colors per vertex
        voxel_size: Size of each voxel

    Returns:
        List of (vx, vy, vz, (r, g, b)) voxel data
    """
    import numpy as np

    vertices = np.array(vertices)
    default_color = (180, 180, 180)

    # Calculate bounding box
    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)

    # Calculate grid
    size = bbox_max - bbox_min
    grid_size = (size / voxel_size).astype(int) + 1

    voxels = []

    # Simple voxelization: check each grid cell
    for gx in range(grid_size[0]):
        for gy in range(grid_size[1]):
            for gz in range(grid_size[2]):
                world_pos = bbox_min + np.array([gx, gy, gz]) * voxel_size + voxel_size / 2

                # Simple distance-based check to vertices
                distances = np.linalg.norm(vertices - world_pos, axis=1)
                min_idx = np.argmin(distances)

                if distances[min_idx] < voxel_size * 1.5:
                    if colors and min_idx < len(colors):
                        color = colors[min_idx]
                    else:
                        color = default_color
                    voxels.append((gx, gy, gz, color))

    return voxels
