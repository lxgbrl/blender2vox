"""
MagicaVoxel .vox File Writer

Based on the official MagicaVoxel file format specification:
https://github.com/ephtracy/voxel-model/blob/master/MagicaVoxel-file-format-vox.txt

File Structure (RIFF style):
- Header: 'VOX ' + version (150)
- MAIN chunk containing:
  - SIZE chunk (model dimensions)
  - XYZI chunk (voxel data)
  - RGBA chunk (palette)
"""

import struct
from typing import List, Tuple, Dict, Optional


class VoxChunk:
    """Represents a chunk in the VOX file format."""
    
    def __init__(self, chunk_id: str, content: bytes = b'', children: bytes = b''):
        self.chunk_id = chunk_id
        self.content = content
        self.children = children
    
    def to_bytes(self) -> bytes:
        """Convert chunk to binary data."""
        # Chunk structure:
        # 4 bytes: chunk id
        # 4 bytes: content size
        # 4 bytes: children size
        # N bytes: content
        # M bytes: children
        
        result = self.chunk_id.encode('ascii')
        result += struct.pack('<I', len(self.content))
        result += struct.pack('<I', len(self.children))
        result += self.content
        result += self.children
        return result


class VoxModel:
    """Represents a single voxel model."""
    
    def __init__(self, size_x: int = 1, size_y: int = 1, size_z: int = 1):
        self.size_x = size_x
        self.size_y = size_y
        self.size_z = size_z
        self.voxels: List[Tuple[int, int, int, int]] = []  # (x, y, z, color_index)
    
    def add_voxel(self, x: int, y: int, z: int, color_index: int):
        """Add a voxel to the model.
        
        Args:
            x, y, z: Voxel coordinates (0-255)
            color_index: Palette color index (1-255, 0 is not used)
        """
        if not (0 <= x < 256 and 0 <= y < 256 and 0 <= z < 256):
            raise ValueError(f"Voxel coordinates must be in range 0-255, got ({x}, {y}, {z})")
        if not (1 <= color_index <= 255):
            raise ValueError(f"Color index must be in range 1-255, got {color_index}")
        
        self.voxels.append((x, y, z, color_index))
    
    def get_size_chunk(self) -> VoxChunk:
        """Generate the SIZE chunk for this model."""
        content = struct.pack('<III', self.size_x, self.size_y, self.size_z)
        return VoxChunk('SIZE', content)
    
    def get_xyzi_chunk(self) -> VoxChunk:
        """Generate the XYZI chunk for this model."""
        content = struct.pack('<I', len(self.voxels))
        for x, y, z, color_index in self.voxels:
            content += struct.pack('<BBBB', x, y, z, color_index)
        return VoxChunk('XYZI', content)


class VoxPalette:
    """Represents a color palette for the VOX file."""
    
    def __init__(self):
        # Initialize with default MagicaVoxel palette
        self.colors: List[Tuple[int, int, int, int]] = self._get_default_palette()
    
    def _get_default_palette(self) -> List[Tuple[int, int, int, int]]:
        """Get the default MagicaVoxel palette."""
        # Default palette values from MagicaVoxel specification
        default = [
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
        
        colors = []
        for val in default:
            # Format is AABBGGRR in the default palette
            a = (val >> 24) & 0xFF
            b = (val >> 16) & 0xFF
            g = (val >> 8) & 0xFF
            r = val & 0xFF
            colors.append((r, g, b, a))
        
        return colors
    
    def set_color(self, index: int, r: int, g: int, b: int, a: int = 255):
        """Set a color in the palette.
        
        Args:
            index: Palette index (1-255, index 0 is reserved)
            r, g, b, a: Color components (0-255)
        """
        if not (1 <= index <= 255):
            raise ValueError(f"Palette index must be in range 1-255, got {index}")
        
        # Note: palette index 0 is unused, so we store at index-1 effectively
        # But for VOX format compatibility, we keep 256 entries
        self.colors[index] = (r, g, b, a)
    
    def get_rgba_chunk(self) -> VoxChunk:
        """Generate the RGBA chunk for this palette.

        In VOX format:
        - File position 0 stores color for index 1
        - File position 1 stores color for index 2
        - ...
        - File position 254 stores color for index 255
        - File position 255 is unused
        """
        content = b''
        # Write 256 RGBA values (1024 bytes)
        for i in range(256):
            # File position i stores color for index i+1
            color_idx = i + 1
            if color_idx < len(self.colors):
                r, g, b, a = self.colors[color_idx]
            else:
                r, g, b, a = 0, 0, 0, 255
            content += struct.pack('<BBBB', r, g, b, a)
        return VoxChunk('RGBA', content)


class VoxWriter:
    """Writes MagicaVoxel .vox files."""
    
    VOX_VERSION = 150
    
    def __init__(self):
        self.models: List[VoxModel] = []
        self.palette = VoxPalette()
    
    def add_model(self, model: VoxModel):
        """Add a model to the file."""
        self.models.append(model)
    
    def write(self, filepath: str):
        """Write the VOX file."""
        with open(filepath, 'wb') as f:
            # Write header
            f.write(b'VOX ')
            f.write(struct.pack('<I', self.VOX_VERSION))
            
            # Build children chunks for MAIN
            children_data = b''
            
            # If multiple models, add PACK chunk
            if len(self.models) > 1:
                pack_content = struct.pack('<I', len(self.models))
                pack_chunk = VoxChunk('PACK', pack_content)
                children_data += pack_chunk.to_bytes()
            
            # Add SIZE and XYZI chunks for each model
            for model in self.models:
                children_data += model.get_size_chunk().to_bytes()
                children_data += model.get_xyzi_chunk().to_bytes()
            
            # Add RGBA palette chunk
            children_data += self.palette.get_rgba_chunk().to_bytes()
            
            # Write MAIN chunk
            main_chunk = VoxChunk('MAIN', b'', children_data)
            f.write(main_chunk.to_bytes())


def create_simple_vox(voxels: List[Tuple[int, int, int, Tuple[int, int, int]]], 
                       filepath: str,
                       size: Optional[Tuple[int, int, int]] = None):
    """Convenience function to create a simple VOX file.
    
    Args:
        voxels: List of (x, y, z, (r, g, b)) tuples
        filepath: Output file path
        size: Optional (size_x, size_y, size_z) tuple. If not provided, calculated from voxels.
    """
    if not voxels:
        raise ValueError("No voxels provided")
    
    # Calculate bounding box if size not provided
    if size is None:
        max_x = max(v[0] for v in voxels) + 1
        max_y = max(v[1] for v in voxels) + 1
        max_z = max(v[2] for v in voxels) + 1
        size = (max_x, max_y, max_z)
    
    # Build color palette from voxels
    color_to_index: Dict[Tuple[int, int, int], int] = {}
    next_index = 1
    
    writer = VoxWriter()
    model = VoxModel(size[0], size[1], size[2])
    
    for x, y, z, color in voxels:
        r, g, b = color
        
        # Get or create palette index for this color
        color_key = (r, g, b)
        if color_key not in color_to_index:
            if next_index > 255:
                # Find closest existing color
                best_index = 1
                best_dist = float('inf')
                for (cr, cg, cb), idx in color_to_index.items():
                    dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best_index = idx
                color_to_index[color_key] = best_index
            else:
                color_to_index[color_key] = next_index
                writer.palette.set_color(next_index, r, g, b, 255)
                next_index += 1
        
        model.add_voxel(x, y, z, color_to_index[color_key])
    
    writer.add_model(model)
    writer.write(filepath)


if __name__ == "__main__":
    # Test: Create a simple colored cube
    test_voxels = []
    for x in range(10):
        for y in range(10):
            for z in range(10):
                # Create gradient colors
                r = int(x / 9 * 255)
                g = int(y / 9 * 255)
                b = int(z / 9 * 255)
                test_voxels.append((x, y, z, (r, g, b)))
    
    create_simple_vox(test_voxels, "test_cube.vox")
    print("Created test_cube.vox")
