"""
VOX Importer for Blender

Imports MagicaVoxel .vox files into Blender with proper vertex colors
and metadata for round-trip export. Supports multi-model files with
scene graph positioning.
"""

import bpy
import bmesh
from typing import List, Tuple, Union
import json
import os

from . import vox_reader


# Custom property name for storing VOX metadata
VOX_METADATA_PROP = "vox_metadata"


def import_vox(filepath: str, scale: float = 0.1,
               create_materials: bool = True,
               use_vertex_colors: bool = True) -> Union[bpy.types.Object, List[bpy.types.Object]]:
    """Import a VOX file into Blender.

    For multi-model files, creates separate objects for each model instance
    positioned according to the scene graph.

    Args:
        filepath: Path to the .vox file
        scale: Scale factor for voxels (default 0.1 = 10cm per voxel)
        create_materials: Create materials for each color
        use_vertex_colors: Apply vertex colors to the mesh

    Returns:
        Single object for single-model files, or list of objects for multi-model files
    """
    # Read the VOX scene with full scene graph support
    scene = vox_reader.read_vox_scene(filepath)

    total_models = len(scene.models)
    total_instances = len(scene.instances)
    print(f"Importing VOX: {total_models} models, {total_instances} instances")

    if total_instances == 0:
        print("Warning: No model instances found in scene")
        return None

    # Create a parent empty for the scene
    base_name = os.path.splitext(os.path.basename(filepath))[0]

    # If only one instance, don't create a parent empty
    if total_instances == 1:
        model_id, translation, rotation, name = scene.instances[0]
        model = scene.models[model_id]

        obj = create_model_object(
            model, scene.palette, scale, use_vertex_colors,
            name if name else base_name
        )

        # Apply translation (convert from voxel units to world units)
        # MagicaVoxel uses center-based positioning, so we need to offset by half the model size
        tx, ty, tz = translation
        # Center offset: MagicaVoxel positions are for the model center
        cx = model.size_x / 2.0
        cy = model.size_y / 2.0
        cz = model.size_z / 2.0
        obj.location = (
            (tx - cx) * scale,
            (ty - cy) * scale,
            (tz - cz) * scale
        )

        # Apply rotation if present
        apply_vox_rotation(obj, rotation)

        store_vox_metadata_for_model(obj, model, scene.palette, filepath)

        if create_materials:
            create_flat_material(obj)

        obj.data.update()
        return obj

    # Multiple instances: create parent empty and child objects
    parent = bpy.data.objects.new(base_name, None)
    parent.empty_display_type = 'PLAIN_AXES'
    bpy.context.collection.objects.link(parent)

    created_objects = []

    for idx, (model_id, translation, rotation, name) in enumerate(scene.instances):
        if model_id >= len(scene.models):
            print(f"Warning: Instance references invalid model {model_id}")
            continue

        model = scene.models[model_id]
        obj_name = name if name else f"{base_name}_{idx}"

        obj = create_model_object(
            model, scene.palette, scale, use_vertex_colors, obj_name
        )

        # Apply translation
        tx, ty, tz = translation
        cx = model.size_x / 2.0
        cy = model.size_y / 2.0
        cz = model.size_z / 2.0
        obj.location = (
            (tx - cx) * scale,
            (ty - cy) * scale,
            (tz - cz) * scale
        )

        # Apply rotation
        apply_vox_rotation(obj, rotation)

        # Parent to the scene empty
        obj.parent = parent

        store_vox_metadata_for_model(obj, model, scene.palette, filepath)

        if create_materials:
            create_flat_material(obj)

        obj.data.update()
        created_objects.append(obj)

    # Select the parent
    bpy.context.view_layer.objects.active = parent
    parent.select_set(True)

    print(f"Created {len(created_objects)} objects")
    return created_objects


def apply_vox_rotation(obj: bpy.types.Object, rotation_index: int):
    """Apply MagicaVoxel rotation to a Blender object.

    MagicaVoxel uses a rotation index (0-23) that encodes axis permutation
    and sign flips. The rotation is stored as a byte with:
    - bits 0-1: index of first row non-zero entry
    - bits 2-3: index of second row non-zero entry
    - bit 4: sign of first row entry (0=positive, 1=negative)
    - bit 5: sign of second row entry
    - bit 6: sign of third row entry

    Args:
        obj: The Blender object to rotate
        rotation_index: MagicaVoxel rotation index
    """
    if rotation_index == 0:
        return  # No rotation

    import mathutils
    import math

    # Decode rotation index
    idx1 = rotation_index & 0x3
    idx2 = (rotation_index >> 2) & 0x3
    sign1 = -1 if (rotation_index >> 4) & 0x1 else 1
    sign2 = -1 if (rotation_index >> 5) & 0x1 else 1
    sign3 = -1 if (rotation_index >> 6) & 0x1 else 1

    # Build rotation matrix
    # The third index is the remaining one (0, 1, or 2 not used by idx1 or idx2)
    idx3 = 3 - idx1 - idx2

    # Build the 3x3 rotation matrix
    mat = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    mat[0][idx1] = sign1
    mat[1][idx2] = sign2
    mat[2][idx3] = sign3

    # Convert to Blender matrix
    rot_matrix = mathutils.Matrix([
        [mat[0][0], mat[0][1], mat[0][2]],
        [mat[1][0], mat[1][1], mat[1][2]],
        [mat[2][0], mat[2][1], mat[2][2]]
    ])

    # Apply rotation
    obj.rotation_euler = rot_matrix.to_euler()


def create_model_object(model: vox_reader.VoxModel,
                        palette: List[Tuple[int, int, int, int]],
                        scale: float,
                        use_vertex_colors: bool,
                        name: str) -> bpy.types.Object:
    """Create a Blender object from a VoxModel.

    Args:
        model: The VoxModel to create
        palette: Color palette
        scale: Scale factor
        use_vertex_colors: Whether to apply vertex colors
        name: Object name

    Returns:
        The created Blender object
    """
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    obj = bpy.data.objects.new(name, mesh)

    bpy.context.collection.objects.link(obj)

    # Build voxel cubes
    voxel_face_colors = []
    bm = bmesh.new()
    face_idx = 0

    for x, y, z, color_idx in model.voxels:
        faces_created = create_voxel_cube_fast(bm, x, y, z, scale)
        voxel_face_colors.append((face_idx, faces_created, color_idx))
        face_idx += faces_created

    bm.to_mesh(mesh)
    bm.free()

    if use_vertex_colors:
        add_vertex_colors_for_model(mesh, palette, voxel_face_colors)

    return obj


def add_vertex_colors_for_model(mesh: bpy.types.Mesh,
                                 palette: List[Tuple[int, int, int, int]],
                                 voxel_face_colors: List[Tuple[int, int, int]]):
    """Add vertex colors to a mesh using a palette.

    Args:
        mesh: The Blender mesh
        palette: Color palette (list of RGBA tuples)
        voxel_face_colors: List of (face_start_idx, face_count, color_idx) per voxel
    """
    if hasattr(mesh, 'color_attributes'):
        if not mesh.color_attributes:
            mesh.color_attributes.new(name="VoxelColors", type='BYTE_COLOR', domain='CORNER')
        color_layer = mesh.color_attributes.active_color
    else:
        if not mesh.vertex_colors:
            mesh.vertex_colors.new(name="VoxelColors")
        color_layer = mesh.vertex_colors.active

    face_to_color = {}
    for face_start, face_count, color_idx in voxel_face_colors:
        if 1 <= color_idx <= 255 and (color_idx - 1) < len(palette):
            r, g, b, a = palette[color_idx - 1]
            color = (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        else:
            color = (1.0, 1.0, 1.0, 1.0)
        for fi in range(face_start, face_start + face_count):
            face_to_color[fi] = color

    for poly_idx, poly in enumerate(mesh.polygons):
        color = face_to_color.get(poly_idx, (0.7, 0.7, 0.7, 1.0))
        for loop_idx in poly.loop_indices:
            color_layer.data[loop_idx].color = color


def store_vox_metadata_for_model(obj: bpy.types.Object,
                                  model: vox_reader.VoxModel,
                                  palette: List[Tuple[int, int, int, int]],
                                  filepath: str):
    """Store VOX metadata on an object for a specific model."""
    metadata = {
        "source_file": filepath,
        "size": [model.size_x, model.size_y, model.size_z],
        "voxels": [[x, y, z, c] for x, y, z, c in model.voxels],
        "palette": [[r, g, b, a] for r, g, b, a in palette],
    }
    obj[VOX_METADATA_PROP] = json.dumps(metadata)


def create_voxel_cube_fast(bm: bmesh.types.BMesh, x: int, y: int, z: int,
                            scale: float) -> int:
    """Create a single voxel cube in the bmesh (optimized version).

    Args:
        bm: The BMesh to add to
        x, y, z: Voxel grid coordinates
        scale: Scale factor

    Returns:
        Number of faces created (always 6)
    """
    # Pre-calculate base position
    bx, by, bz = x * scale, y * scale, z * scale
    bx1, by1, bz1 = bx + scale, by + scale, bz + scale

    # Create 8 vertices directly with calculated positions
    v0 = bm.verts.new((bx, by, bz))
    v1 = bm.verts.new((bx1, by, bz))
    v2 = bm.verts.new((bx1, by1, bz))
    v3 = bm.verts.new((bx, by1, bz))
    v4 = bm.verts.new((bx, by, bz1))
    v5 = bm.verts.new((bx1, by, bz1))
    v6 = bm.verts.new((bx1, by1, bz1))
    v7 = bm.verts.new((bx, by1, bz1))

    # Create 6 faces directly (no lookup table needed)
    bm.faces.new((v0, v1, v2, v3))  # Bottom
    bm.faces.new((v4, v7, v6, v5))  # Top
    bm.faces.new((v0, v4, v5, v1))  # Front
    bm.faces.new((v2, v6, v7, v3))  # Back
    bm.faces.new((v0, v3, v7, v4))  # Left
    bm.faces.new((v1, v5, v6, v2))  # Right

    return 6


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
