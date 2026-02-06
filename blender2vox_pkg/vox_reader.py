"""
MagicaVoxel .vox File Reader

Parses VOX files and extracts voxel data, palette, and metadata.
Based on the official MagicaVoxel file format specification.
Supports multi-model files with scene graph (nTRN, nGRP, nSHP chunks).
"""

import struct
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class VoxModel:
    """Container for a single voxel model within a scene."""
    size_x: int
    size_y: int
    size_z: int
    voxels: List[Tuple[int, int, int, int]]  # (x, y, z, color_index)
    # World position from scene graph (translation)
    translation: Tuple[int, int, int] = (0, 0, 0)
    # Rotation index from scene graph
    rotation: int = 0
    # Optional name from attributes
    name: str = ""


@dataclass
class VoxelData:
    """Container for voxel model data (legacy single-model interface)."""
    size_x: int
    size_y: int
    size_z: int
    voxels: List[Tuple[int, int, int, int]]  # (x, y, z, color_index)
    palette: List[Tuple[int, int, int, int]]  # (r, g, b, a) for indices 1-255


@dataclass
class VoxScene:
    """Container for a complete VOX scene with multiple models."""
    models: List[VoxModel] = field(default_factory=list)
    palette: List[Tuple[int, int, int, int]] = field(default_factory=list)
    # Model instances with transforms (model_id, translation, rotation, name)
    instances: List[Tuple[int, Tuple[int, int, int], int, str]] = field(default_factory=list)


def _parse_dict(content: bytes, start_pos: int) -> Tuple[Dict[str, str], int]:
    """Parse a VOX dictionary from binary content.

    Args:
        content: Binary content
        start_pos: Position to start reading

    Returns:
        Tuple of (parsed dict, new position after dict)
    """
    pos = start_pos
    num_attrs = struct.unpack('<I', content[pos:pos+4])[0]
    pos += 4
    attrs = {}
    for _ in range(num_attrs):
        key_len = struct.unpack('<I', content[pos:pos+4])[0]
        pos += 4
        key = content[pos:pos+key_len].decode('ascii', errors='replace')
        pos += key_len
        val_len = struct.unpack('<I', content[pos:pos+4])[0]
        pos += 4
        val = content[pos:pos+val_len].decode('ascii', errors='replace')
        pos += val_len
        attrs[key] = val
    return attrs, pos


def read_vox_scene(filepath: str) -> VoxScene:
    """Read a VOX file and return the complete scene with all models and transforms.

    Args:
        filepath: Path to the .vox file

    Returns:
        VoxScene containing all models with their world positions

    Raises:
        ValueError: If the file is not a valid VOX file
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    magic = data[:4]
    if magic != b'VOX ':
        raise ValueError(f"Not a valid VOX file (magic: {magic})")

    version = struct.unpack('<I', data[4:8])[0]
    if version not in (150, 200):
        print(f"Warning: VOX version {version} (expected 150 or 200)")

    # Parse all chunks
    pos = 8
    chunks = []
    while pos < len(data):
        if pos + 12 > len(data):
            break
        chunk_id = data[pos:pos+4].decode('ascii', errors='replace')
        content_size = struct.unpack('<I', data[pos+4:pos+8])[0]
        # children_size at pos+8:pos+12 - we skip it, just parse linearly
        content_start = pos + 12
        content = data[content_start:content_start + content_size]
        chunks.append({'id': chunk_id, 'content': content})
        pos = content_start + content_size

    # Extract models (SIZE/XYZI pairs)
    models = []
    current_size = None
    palette = get_default_palette()

    for chunk in chunks:
        if chunk['id'] == 'SIZE':
            sx, sy, sz = struct.unpack('<III', chunk['content'][:12])
            current_size = (sx, sy, sz)
        elif chunk['id'] == 'XYZI':
            content = chunk['content']
            num_voxels = struct.unpack('<I', content[:4])[0]
            voxels = []
            for i in range(num_voxels):
                offset = 4 + i * 4
                x, y, z, c = struct.unpack('<BBBB', content[offset:offset + 4])
                voxels.append((x, y, z, c))
            if current_size:
                models.append(VoxModel(
                    size_x=current_size[0],
                    size_y=current_size[1],
                    size_z=current_size[2],
                    voxels=voxels
                ))
        elif chunk['id'] == 'RGBA':
            content = chunk['content']
            palette = []
            for i in range(256):
                offset = i * 4
                r, g, b, a = struct.unpack('<BBBB', content[offset:offset + 4])
                palette.append((r, g, b, a))

    # Parse scene graph to get transforms
    transforms = {}  # node_id -> (child_node_id, translation, rotation, name)
    shape_nodes = {}  # node_id -> model_id

    for chunk in chunks:
        if chunk['id'] == 'nTRN':
            content = chunk['content']
            node_id = struct.unpack('<I', content[:4])[0]
            attrs, pos = _parse_dict(content, 4)
            child_node_id = struct.unpack('<I', content[pos:pos+4])[0]
            pos += 4
            pos += 4  # reserved
            pos += 4  # layer_id
            num_frames = struct.unpack('<I', content[pos:pos+4])[0]
            pos += 4

            frame_attrs = {}
            if num_frames > 0 and pos < len(content):
                frame_attrs, pos = _parse_dict(content, pos)

            # Parse translation "_t" = "x y z"
            translation = (0, 0, 0)
            if '_t' in frame_attrs:
                parts = frame_attrs['_t'].split()
                if len(parts) == 3:
                    translation = (int(parts[0]), int(parts[1]), int(parts[2]))

            # Parse rotation "_r" = rotation index
            rotation = 0
            if '_r' in frame_attrs:
                rotation = int(frame_attrs['_r'])

            name = attrs.get('_name', '')
            transforms[node_id] = (child_node_id, translation, rotation, name)

        elif chunk['id'] == 'nSHP':
            content = chunk['content']
            node_id = struct.unpack('<I', content[:4])[0]
            attrs, pos = _parse_dict(content, 4)
            num_models = struct.unpack('<I', content[pos:pos+4])[0]
            pos += 4
            if num_models > 0:
                model_id = struct.unpack('<I', content[pos:pos+4])[0]
                shape_nodes[node_id] = model_id

    # Build instances: find transforms that point to shape nodes
    instances = []
    for node_id, (child_node_id, translation, rotation, name) in transforms.items():
        if child_node_id in shape_nodes:
            model_id = shape_nodes[child_node_id]
            if model_id < len(models):
                instances.append((model_id, translation, rotation, name))

    # If no scene graph, create a single instance at origin for each model
    if not instances and models:
        for i, model in enumerate(models):
            instances.append((i, (0, 0, 0), 0, f"Model_{i}"))

    return VoxScene(
        models=models,
        palette=palette,
        instances=instances
    )


def read_vox_file(filepath: str) -> VoxelData:
    """Read a VOX file and return its voxel data (legacy single-model interface).

    For multi-model files, this merges all voxels into a single model.
    Use read_vox_scene() for proper multi-model support.

    Args:
        filepath: Path to the .vox file

    Returns:
        VoxelData containing size, voxels, and palette

    Raises:
        ValueError: If the file is not a valid VOX file
    """
    scene = read_vox_scene(filepath)

    if not scene.models:
        return VoxelData(
            size_x=1, size_y=1, size_z=1,
            voxels=[],
            palette=scene.palette if scene.palette else get_default_palette()
        )

    # For legacy compatibility, just return the first model
    model = scene.models[0]
    return VoxelData(
        size_x=model.size_x,
        size_y=model.size_y,
        size_z=model.size_z,
        voxels=model.voxels,
        palette=scene.palette
    )


def get_default_palette() -> List[Tuple[int, int, int, int]]:
    """Get the default MagicaVoxel palette."""
    # Default palette from MagicaVoxel specification
    default_hex = [
        0x00000000, 0xffffffff, 0xffccffff, 0xff99ffff, 0xff66ffff, 0xff33ffff, 0xff00ffff, 0xffffccff,
        0xffccccff, 0xff99ccff, 0xff66ccff, 0xff33ccff, 0xff00ccff, 0xffff99ff, 0xffcc99ff, 0xff9999ff,
        0xff6699ff, 0xff3399ff, 0xff0099ff, 0xffff66ff, 0xffcc66ff, 0xff9966ff, 0xff6666ff, 0xff3366ff,
        0xff0066ff, 0xffff33ff, 0xffcc33ff, 0xff9933ff, 0xff6633ff, 0xff3333ff, 0xff0033ff, 0xffff00ff,
        0xffcc00ff, 0xff9900ff, 0xff6600ff, 0xff3300ff, 0xff0000ff, 0xffffffcc, 0xffccffcc, 0xff99ffcc,
        0xff66ffcc, 0xff33ffcc, 0xff00ffcc, 0xffffcccc, 0xffcccccc, 0xff99cccc, 0xff66cccc, 0xff33cccc,
        0xff00cccc, 0xffff99cc, 0xffcc99cc, 0xff9999cc, 0xff6699cc, 0xff3399cc, 0xff0099cc, 0xffff66cc,
        0xffcc66cc, 0xff9966cc, 0xff6666cc, 0xff3366cc, 0xff0066cc, 0xffff33cc, 0xffcc33cc, 0xff9933cc,
        0xff6633cc, 0xff3333cc, 0xff0033cc, 0xffff00cc, 0xffcc00cc, 0xff9900cc, 0xff6600cc, 0xff3300cc,
        0xff0000cc, 0xffffff99, 0xffccff99, 0xff99ff99, 0xff66ff99, 0xff33ff99, 0xff00ff99, 0xffffcc99,
        0xffcccc99, 0xff99cc99, 0xff66cc99, 0xff33cc99, 0xff00cc99, 0xffff9999, 0xffcc9999, 0xff999999,
        0xff669999, 0xff339999, 0xff009999, 0xffff6699, 0xffcc6699, 0xff996699, 0xff666699, 0xff336699,
        0xff006699, 0xffff3399, 0xffcc3399, 0xff993399, 0xff663399, 0xff333399, 0xff003399, 0xffff0099,
        0xffcc0099, 0xff990099, 0xff660099, 0xff330099, 0xff000099, 0xffffff66, 0xffccff66, 0xff99ff66,
        0xff66ff66, 0xff33ff66, 0xff00ff66, 0xffffcc66, 0xffcccc66, 0xff99cc66, 0xff66cc66, 0xff33cc66,
        0xff00cc66, 0xffff9966, 0xffcc9966, 0xff999966, 0xff669966, 0xff339966, 0xff009966, 0xffff6666,
        0xffcc6666, 0xff996666, 0xff666666, 0xff336666, 0xff006666, 0xffff3366, 0xffcc3366, 0xff993366,
        0xff663366, 0xff333366, 0xff003366, 0xffff0066, 0xffcc0066, 0xff990066, 0xff660066, 0xff330066,
        0xff000066, 0xffffff33, 0xffccff33, 0xff99ff33, 0xff66ff33, 0xff33ff33, 0xff00ff33, 0xffffcc33,
        0xffcccc33, 0xff99cc33, 0xff66cc33, 0xff33cc33, 0xff00cc33, 0xffff9933, 0xffcc9933, 0xff999933,
        0xff669933, 0xff339933, 0xff009933, 0xffff6633, 0xffcc6633, 0xff996633, 0xff666633, 0xff336633,
        0xff006633, 0xffff3333, 0xffcc3333, 0xff993333, 0xff663333, 0xff333333, 0xff003333, 0xffff0033,
        0xffcc0033, 0xff990033, 0xff660033, 0xff330033, 0xff000033, 0xffffff00, 0xffccff00, 0xff99ff00,
        0xff66ff00, 0xff33ff00, 0xff00ff00, 0xffffcc00, 0xffcccc00, 0xff99cc00, 0xff66cc00, 0xff33cc00,
        0xff00cc00, 0xffff9900, 0xffcc9900, 0xff999900, 0xff669900, 0xff339900, 0xff009900, 0xffff6600,
        0xffcc6600, 0xff996600, 0xff666600, 0xff336600, 0xff006600, 0xffff3300, 0xffcc3300, 0xff993300,
        0xff663300, 0xff333300, 0xff003300, 0xffff0000, 0xffcc0000, 0xff990000, 0xff660000, 0xff330000,
        0xff0000ee, 0xff0000dd, 0xff0000bb, 0xff0000aa, 0xff000088, 0xff000077, 0xff000055, 0xff000044,
        0xff000022, 0xff000011, 0xff00ee00, 0xff00dd00, 0xff00bb00, 0xff00aa00, 0xff008800, 0xff007700,
        0xff005500, 0xff004400, 0xff002200, 0xff001100, 0xffee0000, 0xffdd0000, 0xffbb0000, 0xffaa0000,
        0xff880000, 0xff770000, 0xff550000, 0xff440000, 0xff220000, 0xff110000, 0xffeeeeee, 0xffdddddd,
        0xffbbbbbb, 0xffaaaaaa, 0xff888888, 0xff777777, 0xff555555, 0xff444444, 0xff222222, 0xff111111,
    ]

    palette = []
    for val in default_hex:
        # Format is AABBGGRR
        a = (val >> 24) & 0xFF
        b = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        r = val & 0xFF
        palette.append((r, g, b, a))

    return palette


def get_voxel_color(voxel_data: VoxelData, color_index: int) -> Tuple[int, int, int, int]:
    """Get the RGBA color for a voxel color index.

    Args:
        voxel_data: The VoxelData containing the palette
        color_index: The color index (1-255)

    Returns:
        (r, g, b, a) tuple
    """
    if 1 <= color_index <= 255:
        # In VOX format, color index 1 maps to palette[0]
        return voxel_data.palette[color_index - 1]
    return (255, 255, 255, 255)  # Default white
