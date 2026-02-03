# Blender2Vox - Blender to MagicaVoxel .vox Import/Export
# Import and export Blender meshes to/from MagicaVoxel .vox format

bl_info = {
    "name": "Blender2Vox - MagicaVoxel Import/Export",
    "author": "Alex Gabriel",
    "version": (2, 0, 0),
    "blender": (2, 80, 0),
    "location": "File > Import/Export > MagicaVoxel (.vox)",
    "description": "Import and export MagicaVoxel .vox files with proper round-trip support",
    "warning": "",
    "doc_url": "https://github.com/StudioGabrielDev/blender2vox",
    "tracker_url": "https://github.com/StudioGabrielDev/blender2vox/issues",
    "category": "Import-Export",
}

import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
)
from bpy_extras.io_utils import ExportHelper, ImportHelper
import os

# Import our modules
if "bpy" in locals():
    import importlib
    if "vox_exporter" in locals():
        importlib.reload(vox_exporter)
    if "vox_writer" in locals():
        importlib.reload(vox_writer)
    if "vox_reader" in locals():
        importlib.reload(vox_reader)
    if "vox_importer" in locals():
        importlib.reload(vox_importer)

from . import vox_exporter
from . import vox_writer
from . import vox_reader
from . import vox_importer


class IMPORT_OT_vox(bpy.types.Operator, ImportHelper):
    """Import MagicaVoxel .vox file"""
    bl_idname = "import_scene.vox"
    bl_label = "Import VOX"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".vox"
    filter_glob: StringProperty(
        default="*.vox",
        options={'HIDDEN'},
        maxlen=255,
    )

    # Import options
    scale: FloatProperty(
        name="Scale",
        description="Scale factor for voxels (1.0 = 1 unit per voxel)",
        default=0.1,
        min=0.001,
        max=10.0,
    )

    create_materials: BoolProperty(
        name="Create Materials",
        description="Create a material that uses vertex colors",
        default=True,
    )

    use_vertex_colors: BoolProperty(
        name="Apply Vertex Colors",
        description="Apply colors from palette as vertex colors",
        default=True,
    )

    def execute(self, context):
        try:
            obj = vox_importer.import_vox(
                filepath=self.filepath,
                scale=self.scale,
                create_materials=self.create_materials,
                use_vertex_colors=self.use_vertex_colors,
            )

            # Set a nice name based on filename
            name = os.path.splitext(os.path.basename(self.filepath))[0]
            obj.name = name

            self.report({'INFO'}, f"Imported {self.filepath}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        box = layout.box()
        box.label(text="Import Settings", icon='IMPORT')
        box.prop(self, "scale")
        box.prop(self, "create_materials")
        box.prop(self, "use_vertex_colors")


class EXPORT_OT_vox(bpy.types.Operator, ExportHelper):
    """Export selected objects to MagicaVoxel .vox format"""
    bl_idname = "export_scene.vox"
    bl_label = "Export VOX"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".vox"
    filter_glob: StringProperty(
        default="*.vox",
        options={'HIDDEN'},
        maxlen=255,
    )

    # Export options
    voxel_size: FloatProperty(
        name="Voxel Size",
        description="Size of each voxel in Blender units. Smaller values create more detailed models",
        default=0.1,
        min=0.001,
        max=10.0,
    )

    max_size: IntProperty(
        name="Max Model Size",
        description="Maximum dimension of the voxel model (MagicaVoxel supports up to 256)",
        default=126,
        min=1,
        max=256,
    )

    use_vertex_colors: BoolProperty(
        name="Use Vertex Colors",
        description="Use vertex colors if available, otherwise use material colors",
        default=True,
    )

    use_material_colors: BoolProperty(
        name="Use Material Base Color",
        description="Extract colors from material base color",
        default=True,
    )

    center_model: BoolProperty(
        name="Center Model",
        description="Center the voxelized model at origin",
        default=True,
    )

    apply_transforms: BoolProperty(
        name="Apply Transforms",
        description="Apply object transforms before voxelization",
        default=True,
    )

    export_selected_only: BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=True,
    )

    fill_interior: BoolProperty(
        name="Fill Interior",
        description="Fill the interior of closed meshes (slower)",
        default=False,
    )

    ray_samples: IntProperty(
        name="Ray Samples",
        description="Number of ray samples for surface detection (higher = more accurate but slower)",
        default=3,
        min=1,
        max=10,
    )

    palette_mode: EnumProperty(
        name="Palette Mode",
        description="How to generate the color palette",
        items=[
            ('AUTO', "Auto Generate", "Automatically generate palette from mesh colors"),
            ('QUANTIZE', "Quantize Colors", "Reduce colors to fit in 255 palette entries"),
        ],
        default='QUANTIZE',
    )

    preserve_vox_data: BoolProperty(
        name="Preserve VOX Data",
        description="If the mesh was imported from VOX, preserve exact voxel positions (recommended for round-trip)",
        default=True,
    )

    def execute(self, context):
        # Collect objects to export
        if self.export_selected_only:
            objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        else:
            objects = [obj for obj in context.scene.objects if obj.type == 'MESH']

        if not objects:
            self.report({'ERROR'}, "No mesh objects to export")
            return {'CANCELLED'}

        try:
            # Create exporter
            exporter = vox_exporter.VoxExporter(
                voxel_size=self.voxel_size,
                max_size=self.max_size,
                use_vertex_colors=self.use_vertex_colors,
                use_material_colors=self.use_material_colors,
                center_model=self.center_model,
                apply_transforms=self.apply_transforms,
                fill_interior=self.fill_interior,
                ray_samples=self.ray_samples,
                palette_mode=self.palette_mode,
                preserve_vox_data=self.preserve_vox_data,
            )

            # Perform export
            exporter.export(objects, self.filepath)

            self.report({'INFO'}, f"Exported to {self.filepath}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        # Check if any selected objects have VOX metadata
        has_vox_metadata = False
        if self.export_selected_only:
            objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
        else:
            objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']

        for obj in objects:
            if vox_importer.VOX_METADATA_PROP in obj:
                has_vox_metadata = True
                break

        # Round-trip settings (show prominently if VOX data detected)
        if has_vox_metadata:
            box = layout.box()
            box.label(text="VOX Data Detected", icon='INFO')
            box.prop(self, "preserve_vox_data")
            if self.preserve_vox_data:
                box.label(text="Will use original voxel positions", icon='CHECKMARK')

        # Voxelization settings (only relevant if not preserving VOX data)
        box = layout.box()
        box.label(text="Voxelization Settings", icon='MESH_GRID')
        if has_vox_metadata and self.preserve_vox_data:
            box.enabled = False
            box.label(text="(Disabled when preserving VOX data)")
        box.prop(self, "voxel_size")
        box.prop(self, "max_size")
        box.prop(self, "ray_samples")
        box.prop(self, "fill_interior")

        # Color settings
        box = layout.box()
        box.label(text="Color Settings", icon='COLOR')
        box.prop(self, "use_vertex_colors")
        box.prop(self, "use_material_colors")
        box.prop(self, "palette_mode")

        # Transform settings
        box = layout.box()
        box.label(text="Transform Settings", icon='OBJECT_DATA')
        box.prop(self, "center_model")
        box.prop(self, "apply_transforms")
        box.prop(self, "export_selected_only")


def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_vox.bl_idname, text="MagicaVoxel (.vox)")


def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_vox.bl_idname, text="MagicaVoxel (.vox)")


classes = (
    IMPORT_OT_vox,
    EXPORT_OT_vox,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
