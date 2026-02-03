# Blender2Vox

A Blender addon for importing and exporting MagicaVoxel `.vox` files with full round-trip support.

![Blender](https://img.shields.io/badge/Blender-2.80%2B-orange)
![License](https://img.shields.io/badge/License-MIT-blue)

## Features

### Import
- Load `.vox` files directly into Blender
- Voxels converted to cube meshes with vertex colors
- Flat/unlit material for accurate MagicaVoxel-like display
- Original voxel data stored as metadata for perfect round-trip export

### Export
- Export Blender meshes to `.vox` format
- **Round-trip support**: Imported VOX files export with exact original colors and positions
- Voxelize arbitrary meshes using ray-casting
- Supports vertex colors and material base colors
- Automatic color palette quantization (max 255 colors)

## Installation

### Method 1: Install from ZIP

1. Download the latest release `.zip` file
2. In Blender, go to `Edit > Preferences > Add-ons`
3. Click `Install...` and select the ZIP file
4. Enable the addon "Import-Export: Blender2Vox - MagicaVoxel Import/Export"

### Method 2: Manual Installation

1. Download or clone this repository
2. Copy the `blender2vox` folder to your Blender addons directory:
   - **macOS**: `~/Library/Application Support/Blender/<version>/scripts/addons/`
   - **Windows**: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
   - **Linux**: `~/.config/blender/<version>/scripts/addons/`
3. Restart Blender
4. Enable the addon in `Edit > Preferences > Add-ons`

## Usage

### Importing VOX Files

1. Go to `File > Import > MagicaVoxel (.vox)`
2. Select your `.vox` file
3. Adjust import settings:
   - **Scale**: Size of each voxel in Blender units (default 0.1)
   - **Create Materials**: Creates a flat material using vertex colors
   - **Apply Vertex Colors**: Applies palette colors as vertex colors

### Exporting to VOX

1. Select the mesh object(s) you want to export
2. Go to `File > Export > MagicaVoxel (.vox)`
3. Configure export settings

#### Round-Trip Export (Recommended for imported VOX files)

When exporting a mesh that was imported from a VOX file:
- **Preserve VOX Data** is enabled by default
- The export panel will show "VOX Data Detected"
- Original voxel positions and colors are preserved exactly

#### Voxelizing Arbitrary Meshes

For meshes not imported from VOX:
- **Voxel Size**: Controls resolution (smaller = more detail, slower)
- **Max Model Size**: Maximum dimension (MagicaVoxel max is 256)
- **Ray Samples**: Accuracy of surface detection
- **Fill Interior**: Fill inside of closed meshes

#### Color Settings

- **Use Vertex Colors**: Extract colors from vertex color layers
- **Use Material Base Color**: Extract colors from Principled BSDF materials
- **Palette Mode**: How to handle color quantization

## Troubleshooting

### Colors look different after export
- Ensure **Preserve VOX Data** is enabled when exporting imported VOX files
- The mesh must have been imported using this addon (not a different VOX importer)

### Model appears black in MagicaVoxel
- Objects without color data use a visible light gray (RGB 180, 180, 180)
- Ensure your mesh has vertex colors or materials with base colors

### Model has holes or missing voxels
- Reduce voxel size for more detail
- Increase ray samples
- Enable "Fill Interior" for closed meshes

### Export is slow
- Increase voxel size
- Reduce max model size
- Reduce ray samples

## Technical Notes

- VOX format uses 1-based color indices (1-255)
- Maximum model size: 256×256×256 voxels
- Maximum palette: 255 colors
- Uses Emission shader for flat/unlit viewport display

## File Structure

```
blender2vox/
├── __init__.py       # Addon registration and UI
├── vox_reader.py     # VOX file parser
├── vox_writer.py     # VOX file writer
├── vox_importer.py   # Blender import logic
├── vox_exporter.py   # Blender export/voxelization logic
└── README.md
```

## Version History

### v2.0.0
- Added VOX file import support
- Round-trip export preserves original voxel data and colors
- Fixed color mapping issues
- Flat/emission material for accurate color display
- Per-face vertex coloring for correct voxel colors

### v1.0.0
- Initial release with export support

## Credits & Acknowledgments

- **MagicaVoxel** by ephtracy: https://ephtracy.github.io/
- **VOX file format specification**: https://github.com/ephtracy/voxel-model

### Based on

This project was inspired by and incorporates concepts from:

- **[blender_magicavoxel](https://github.com/AstrorEnales/blender_magicavoxel)** by AstrorEnales
  - Original MagicaVoxel importer for Blender
  - Copyright (c) 2022-2026 AstrorEnales
  - Licensed under MIT License

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2024-2026 Studio Gabriel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
