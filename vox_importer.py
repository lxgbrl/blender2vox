"""
VOX Importer for Blender

Imports MagicaVoxel .vox files into Blender with proper vertex colors
and metadata for round-trip export.
"""

import bpy
import bmesh
from mathutils import Vector
from typing import List, Tuple, Dict, Set
import json

from . import vox_reader


# Custom property name for storing VOX metadata
VOX_METADATA_PROP = "vox_metadata"


def import_vox(filepath: str, scale: float = 0.1,
               create_materials: bool = True,
               use_vertex_colors: bool = True) -> bpy.types.Object:
    """Import a VOX file into Blender.

    Args:
        filepath: Path to the .vox file
        scale: Scale factor for voxels (default 0.1 = 10cm per voxel)
        create_materials: Create materials for each color
        use_vertex_colors: Apply vertex colors to the mesh

    Returns:
        The created Blender object
    """
    # Read the VOX file
    vox_data = vox_reader.read_vox_file(filepath)

    print(f"Importing VOX: {vox_data.size_x}x{vox_data.size_y}x{vox_data.size_z}, "
          f"{len(vox_data.voxels)} voxels")

    # Create mesh
    mesh = bpy.data.meshes.new("VOX_Mesh")
    obj = bpy.data.objects.new("VOX_Model", mesh)

    # Link to scene
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Build voxel cubes - store voxel info for color assignment
    voxel_face_colors = []  # List of (face_start_idx, color_idx) for each voxel

    bm = bmesh.new()
    face_count = 0

    # Create voxel cubes and track face indices
    for x, y, z, color_idx in vox_data.voxels:
        face_start = len(bm.faces)
        create_voxel_cube(bm, x, y, z, scale)
        bm.faces.ensure_lookup_table()
        faces_created = len(bm.faces) - face_start
        voxel_face_colors.append((face_start, faces_created, color_idx))

    # Update mesh
    bm.to_mesh(mesh)
    bm.free()

    # Add vertex colors per face (not per vertex position)
    if use_vertex_colors:
        add_vertex_colors_per_face(mesh, vox_data, voxel_face_colors)

    # Store VOX metadata for round-trip export
    store_vox_metadata(obj, vox_data, filepath)

    # Create materials if requested
    if create_materials:
        create_flat_material(obj)

    # Update mesh
    mesh.update()

    return obj


def create_voxel_cube(bm: bmesh.types.BMesh, x: int, y: int, z: int,
                       scale: float) -> List[bmesh.types.BMVert]:
    """Create a single voxel cube in the bmesh.

    Args:
        bm: The BMesh to add to
        x, y, z: Voxel grid coordinates
        scale: Scale factor

    Returns:
        List of created vertices
    """
    # Cube corner offsets
    offsets = [
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),  # Bottom face
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),  # Top face
    ]

    # Create vertices
    verts = []
    for ox, oy, oz in offsets:
        pos = Vector((
            (x + ox) * scale,
            (y + oy) * scale,
            (z + oz) * scale
        ))
        verts.append(bm.verts.new(pos))

    bm.verts.ensure_lookup_table()

    # Create faces (indices into verts list)
    face_indices = [
        (0, 1, 2, 3),  # Bottom
        (4, 7, 6, 5),  # Top
        (0, 4, 5, 1),  # Front
        (2, 6, 7, 3),  # Back
        (0, 3, 7, 4),  # Left
        (1, 5, 6, 2),  # Right
    ]

    for indices in face_indices:
        face_verts = [verts[i] for i in indices]
        try:
            bm.faces.new(face_verts)
        except ValueError:
            # Face already exists (shared between cubes)
            pass

    return verts


def add_vertex_colors_per_face(mesh: bpy.types.Mesh, vox_data: vox_reader.VoxelData,
                               voxel_face_colors: List[Tuple[int, int, int]]):
    """Add vertex colors to the mesh, coloring each voxel's faces uniformly.

    Args:
        mesh: The Blender mesh
        vox_data: VOX data with palette
        voxel_face_colors: List of (face_start_idx, face_count, color_idx) per voxel
    """
    # Create vertex color layer using the appropriate API
    if hasattr(mesh, 'color_attributes'):
        # Blender 3.2+ API
        if not mesh.color_attributes:
            mesh.color_attributes.new(name="VoxelColors", type='BYTE_COLOR', domain='CORNER')
        color_layer = mesh.color_attributes.active_color
    else:
        # Old API
        if not mesh.vertex_colors:
            mesh.vertex_colors.new(name="VoxelColors")
        color_layer = mesh.vertex_colors.active

    # Build face index to color mapping
    face_to_color = {}
    for face_start, face_count, color_idx in voxel_face_colors:
        r, g, b, a = vox_reader.get_voxel_color(vox_data, color_idx)
        color = (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        for fi in range(face_start, face_start + face_count):
            face_to_color[fi] = color

    # Apply colors to all loops of each face
    for poly_idx, poly in enumerate(mesh.polygons):
        color = face_to_color.get(poly_idx, (0.7, 0.7, 0.7, 1.0))
        for loop_idx in poly.loop_indices:
            color_layer.data[loop_idx].color = color


def store_vox_metadata(obj: bpy.types.Object, vox_data: vox_reader.VoxelData,
                       filepath: str):
    """Store VOX metadata on the object for round-trip export.

    This allows the exporter to preserve exact voxel positions and colors.
    """
    metadata = {
        "source_file": filepath,
        "size": [vox_data.size_x, vox_data.size_y, vox_data.size_z],
        "voxels": [[x, y, z, c] for x, y, z, c in vox_data.voxels],
        "palette": [[r, g, b, a] for r, g, b, a in vox_data.palette],
    }

    # Store as JSON string in custom property
    obj[VOX_METADATA_PROP] = json.dumps(metadata)


def get_vox_metadata(obj: bpy.types.Object) -> dict:
    """Retrieve VOX metadata from an object if available.

    Returns:
        Dict with VOX metadata, or empty dict if not available
    """
    if VOX_METADATA_PROP in obj:
        try:
            return json.loads(obj[VOX_METADATA_PROP])
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def create_flat_material(obj: bpy.types.Object):
    """Create a flat/unlit material using vertex colors (like MagicaVoxel).

    Uses an Emission shader to display colors without shading.

    Args:
        obj: The Blender object
    """
    # Create a material that uses vertex colors with emission (flat/unlit)
    mat_name = "VOX_Flat"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

        # Set up node tree for flat vertex colors
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Clear default nodes
        nodes.clear()

        # Create nodes
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (400, 0)

        # Use Emission for completely flat/unlit look
        emission = nodes.new('ShaderNodeEmission')
        emission.location = (200, 0)
        emission.inputs['Strength'].default_value = 1.0

        vertex_color = nodes.new('ShaderNodeVertexColor')
        vertex_color.location = (0, 0)
        vertex_color.layer_name = "VoxelColors"

        # Link: Vertex Color -> Emission -> Output
        links.new(vertex_color.outputs['Color'], emission.inputs['Color'])
        links.new(emission.outputs['Emission'], output.inputs['Surface'])

    # Assign material to object
    if mat.name not in [slot.name for slot in obj.material_slots if slot.material]:
        obj.data.materials.append(mat)
