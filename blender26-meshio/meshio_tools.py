
# coding: utf-8

# 
# Copyright (c) 2011-2012 griffon
# 
# This software is provided 'as-is', without any express or implied
# warranty. In no event will the authors be held liable for any damages
# arising from the use of this software.
# 
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
# 
#  1. The origin of this software must not be misrepresented; you must not
#     claim that you wrote the original software. If you use this software
#     in a product, an acknowledgment in the product documentation would be
#     appreciated but is not required.
#  2. Altered source versions must be plainly marked as such, and must not be
#     misrepresented as being the original software.
#  3. This notice may not be removed or altered from any source distribution.
# 

# See also
# http://www.blender.org/education-help/faq/gpl-for-artists
#

import traceback
import os

import bpy

from . import pymeshio
from . import bl
from . import export_extender

def _index_of(_bpy_prop_collection, obj):
    for index, item in enumerate(_bpy_prop_collection):
        if item == obj:
            return index
    return -1

class BLTextureManager:
    """Utility Class for Blender Texture"""
    
    @classmethod
    def pmd_path_to_blender_path(cls, pmd_filepath):
        return bpy.path.relpath(pmd_filepath)
    
    @classmethod
    def texture_is_path(cls, texture, pmd_filepath):
        if not texture or texture.type != 'IMAGE' or texture.image is None:
            return False
        return texture.image.filepath == cls.pmd_path_to_blender_path(pmd_filepath)
    
    @classmethod
    def texture_is_changed(cls, texture, pmd_filepath):
        return ( texture is None ) or not cls.texture_is_path(texture, pmd_filepath)
    
    @classmethod
    def texture_is_spa(cls, texture):
        return texture and texture.type == 'IMAGE' and texture.image \
                and texture.image.filepath.lower().endswith(".spa")
    
    DUMMY_IMAGE_NAME = "Image"
    
    @classmethod
    def get_image_dummy(cls):
        if cls.DUMMY_IMAGE_NAME in bpy.data.images:
            return bpy.data.images[cls.DUMMY_IMAGE_NAME]
        else:
            return bpy.data.images.new(cls.DUMMY_IMAGE_NAME, width=16, height=16)
    
    @classmethod
    def get_image_for_texture(cls, pmd_filepath):
        path = cls.pmd_path_to_blender_path(pmd_filepath)
        # Search Images already loaded.
        image = next( (im for im in bpy.data.images if im.filepath == path), None)
        if not image:
            try: # Try to load a new image.
                image = bpy.data.images.load(path)
            except: # Failed.
                print("WARNING: Texture loading faild. > ", pmd_filepath)
        return image
    
    @classmethod
    def create_texture_default(cls, pmd_filepath):
        image = cls.get_image_for_texture(pmd_filepath)
        image = cls.get_image_dummy() if not image else image # Fallback
        tex = bpy.data.textures.new(bpy.path.basename(pmd_filepath), 'IMAGE')
        tex.image = image
        #tex.use_mipmap = True
        tex.use_interpolation = True
        tex.use_alpha = True
        return tex
    
    @classmethod
    def create_texture_toon(cls, toon_name):
        if toon_name in bpy.data.textures:
            return bpy.data.textures[toon_name]
        # Create new Texture
        tex = bpy.data.textures.new(toon_name, 'IMAGE')
        tex.image = cls.get_image_dummy()
        return tex

FIND_SLOT_DEFAULT = lambda i, slot, enabled: slot.texture_coords == 'UV' and enabled
FIND_SLOT_SPHERE = lambda i, slot, enabled: slot.mapping == 'SPHERE' and enabled
FIND_SLOT_TOON = lambda i, slot, enabled: not enabled

class BLMaterial:
    """Utility Wrapper Class for Blender Material"""
    def __init__(self, material):
        self._m = material
    
    def each_texture_slots(self):
        """Generator function (index, texture_slot, enabled)"""
        for i, slot in enumerate(self._m.texture_slots):
            if slot:
                yield i, slot, slot.use
    
    def find_texture_slot(self, test_func):
        return next( iter( i for i, slot, enabled in self.each_texture_slots() if test_func(i, slot, enabled) ), -1)
    
    def new_texture_slot(self, enabled, slot_index = -1):
        slot = self._m.texture_slots.add() if slot_index < 0 else self._m.texture_slots.create(slot_index)
        slot.use = enabled
        return _index_of(self._m.texture_slots, slot)
    
    def ensure_texture_slot_exists(self, slot_index, enabled):
        """Create new TextureSlot if slot_index is invalid."""
        if slot_index < 0 or not self._m.texture_slots[slot_index]:
            return self.new_texture_slot(enabled, slot_index)
        else:
            return slot_index
    
    def clear_texture_slot(self, slot_index):
        """Clear TextureSlot if slot_index is valid."""
        if slot_index >= 0:
            self._m.texture_slots.clear(slot_index)
    
    def set_texture(self, slot_index, texture, tex_type='DEFAULT'):
        if slot_index >= 0 and texture:
            slot = self._m.texture_slots[slot_index]
            slot.texture = texture
            if tex_type == 'DEFAULT' or tex_type == 'TOON':
                slot.texture_coords = 'UV'
                slot.mapping = 'FLAT'
                slot.blend_type = 'MULTIPLY'
                slot.use_map_alpha = True
            elif tex_type == 'SPHERE':
                slot.texture_coords = 'NORMAL'
                slot.mapping = 'SPHERE'
                slot.blend_type = 'ADD' if BLTextureManager.texture_is_spa(texture) else 'MULTIPLY'
    
    def get_texture(self, slot_index):
        return self._m.texture_slots[slot_index].texture
    
class PMDToonTextureManager:
    """Utility Class for Managing PMD Toon Textures"""
    
    @classmethod
    def ensure_toon_texture_obj_exists(cls):
        if export_extender.get_toon_mesh_object():
            return # Already exists.
        # Create new Toon Texture Object
        dummy_mesh = bpy.data.meshes.new("Mesh")
        toon_tex_obj = bpy.data.objects.new(bl.TOON_TEXTURE_OBJECT, dummy_mesh)
        bpy.context.scene.objects.link(toon_tex_obj)
        toon_material = bpy.data.materials.new(bl.TOON_TEXTURE_OBJECT)
        bl.mesh.addMaterial(dummy_mesh, toon_material)
    
    @classmethod
    def set_toon_name(cls, index, toon_name):
        m = BLMaterial(export_extender.get_toon_material())
        m.ensure_texture_slot_exists(index, False)
        if toon_name and len(toon_name) > 0:
            tex = m.get_texture(index)
            if not tex or tex.name != toon_name:
                tex = BLTextureManager.create_texture_toon(toon_name)
                m.set_texture(index, tex, 'TOON')
        else:
            m.set_texture(index, None, 'TOON')


def _pmd_material_feedback_texture(bl_material, toon_index, tex_path="", sphere_path=""):
    # NOTE: UV Mapping Settings are not feedbacked.
    m = BLMaterial(bl_material)
    ### Texture ###
    slot_index = m.find_texture_slot(FIND_SLOT_DEFAULT)
    if len(tex_path) > 0: # PMD Material has a texture.
        # Create new TextureSlot IF it does not exist.
        slot_index = m.ensure_texture_slot_exists(slot_index, True)
        # Set new Texture to TextureSlot.
        if BLTextureManager.texture_is_changed(m.get_texture(slot_index), tex_path):
            # Create new Texture
            tex = BLTextureManager.create_texture_default(tex_path)
            m.set_texture(slot_index, tex, 'DEFAULT')
    elif slot_index >= 0: # PMD Material does not have a texture.
        # Remove old TextureSlot.
        m.clear_texture_slot(slot_index)
    
    ### Sphere Mapping ###
    slot_index = m.find_texture_slot(FIND_SLOT_SPHERE)
    if len(sphere_path) > 0:
        # Create new TextureSlot IF it does not exist.
        slot_index = m.ensure_texture_slot_exists(slot_index, True)
        # Set new Texture to TextureSlot.
        if BLTextureManager.texture_is_changed(m.get_texture(slot_index), sphere_path):
            # Create new Texture
            tex = BLTextureManager.create_texture_default(sphere_path)
            m.set_texture(slot_index, tex, 'SPHERE')
    elif slot_index >= 0: # PMD Material does not have a sphere mapping.
        # Remove old TextureSlot.
        m.clear_texture_slot(slot_index)
    
    ### ToonTexture ###
    slot_index = m.find_texture_slot(FIND_SLOT_TOON)
    toon_material = export_extender.get_toon_material()
    # Check ToonTexture Obj exists.
    if toon_material:
        toon_m = BLMaterial(toon_material)
        # Create new TextureSlot IF it does not exist.
        slot_index = m.ensure_texture_slot_exists(slot_index, False)
        # Set Texture to TextureSlot.
        m.set_texture(slot_index, toon_m.get_texture(toon_index), 'TOON')
    return

def _pmd_material_feedback(pmd_material, bl_material, basedir):
    def _get_RGB(color):
        return [ color.r, color.g, color.b ]
    bl_material.diffuse_shader = "FRESNEL"
    bl_material.diffuse_color = _get_RGB(pmd_material.diffuse_color)
    bl_material.alpha = pmd_material.alpha
    bl_material.specular_shader = "TOON"
    bl_material.specular_color = _get_RGB(pmd_material.specular_color)
    bl_material.specular_toon_size = int(pmd_material.specular_factor)
    bl_material["material_shinness"] = int(pmd_material.specular_factor)
    bl_material.mirror_color = _get_RGB(pmd_material.ambient_color)
    bl_material.subsurface_scattering.use = (pmd_material.edge_flag == 1)
    bl_material.use_transparency = True
    
    def _resolve_path(basedir, path):
        return "" if len(path) == 0 else os.path.join(basedir, path)
    
    texture_names = pmd_material.texture_file.decode("cp932")
    if len(texture_names) > 0:
        # NOTE: Almost all pmd files will be works well.
        _tex_names = (texture_names + "*").split("*")
        _pmd_material_feedback_texture(bl_material, pmd_material.toon_index,
                _resolve_path(basedir, _tex_names[0]),
                _resolve_path(basedir, _tex_names[1]) )
    else:
        _pmd_material_feedback_texture(bl_material, pmd_material.toon_index)

def _pmd_material_feedback_by_name(pmd_model, mat_index, bl_mat_name, basedir):
    if (0 <= mat_index) and (mat_index < len(pmd_model.materials)):
        pmd_mat = pmd_model.materials[mat_index]
    else: # Index out of range
        return
    # Prepare Blender Material (create new one when the material does't exists.)
    if bl_mat_name in bpy.data.materials:
        bl_mat = bpy.data.materials[bl_mat_name]
    else:
        bl_mat = bpy.data.materials.new(bl_mat_name)
    # Initialize material parameters
    _pmd_material_feedback(pmd_mat, bl_mat, basedir)

def _pmd_toon_textures_feedback(pmd_model):
    PMDToonTextureManager.ensure_toon_texture_obj_exists()
    for index, toon_name_bytes in enumerate(pmd_model.toon_textures):
        toon_name = bpy.path.basename(toon_name_bytes.decode('cp932'))
        PMDToonTextureManager.set_toon_name(index, toon_name)

class PmdMaterialFeedbackOperator(bpy.types.Operator):
    '''Feedback Material Settings From PMD File'''
    bl_idname = "material.feedback_pmd"
    bl_label = "Feedback PMD Materials to Blender"
    bl_options = { 'REGISTER' }
    
    class MFeedbackParameter(bpy.types.PropertyGroup):
        enable = bpy.props.BoolProperty(name="Import", default=False)
        index  = bpy.props.IntProperty(name="PMD Material Index", min=-1, max=255, default=0)
        name   = bpy.props.StringProperty(name='Blender Material Name', default="")
    
    material_pairs = bpy.props.CollectionProperty(type=MFeedbackParameter)
    filepath = bpy.props.StringProperty(name='PMD File Path', subtype="FILE_PATH")
    toon_textures = bpy.props.BoolProperty(name="Toon Textures Setting", default=True)
    
    def __init__(self):
        self.__model = None
    def __get_model(self):
        '''Read PMD Model with pymeshio'''
        if (not self.__model) and (self.filepath != ""):
            try:
                _file_realpath = bpy.path.abspath(self.filepath)
                self.__model = pymeshio.pmd.reader.read_from_file(_file_realpath)
            except:
                traceback.print_exc()
        return self.__model
    def __clear_model(self):
        self.__model = None
    
    def execute(self, context):
        if not self.__get_model():
            return { 'CANCELLED' }
        _base_dirpath = os.path.dirname(bpy.path.abspath(self.filepath))
        # Feedback Toon Textures
        if self.toon_textures:
            _pmd_toon_textures_feedback(self.__get_model())
        # Feedback Materials
        for item in self.material_pairs:
            if (not item.enable) or (len(item.name) <= 0):
                continue
            _pmd_material_feedback_by_name(self.__get_model(), item.index, item.name, _base_dirpath)
            
        self.__clear_model()
        return { 'FINISHED' }
    
    def invoke(self, context, event):
        if not self.__get_model():
            return { 'CANCELLED' } # Model loading is failed.
        else: # Success! Continue...
            # Load Last Export Information
            ex_info = export_extender.ExportInfo.load().materials
            for i, m in enumerate(self.__get_model().materials):
                item = self.material_pairs.add()
                item.index = i
                item.name = ex_info[i]["name"] if i < len(ex_info) else ""
            return context.window_manager.invoke_props_dialog(self, width=500)
    
    def draw(self, context):
        layout = self.layout
        layout.label("filepath: " + self.filepath)
        for item in self.material_pairs:
            row = layout.row()
            col=row.column()
            col.alignment = "LEFT"
            col.prop(item, "enable")
            col=row.column()
            col.alignment = "LEFT"
            col.prop(item, "index",text="Index")
            row.column().prop(item, "name", text="Name", icon="MATERIAL")
        layout.row().prop(self, "toon_textures")


class PmdMaterialFeedbackCmdOperator(bpy.types.Operator):
    '''Feedback Material Settings From PMD File'''
    bl_idname = "material.feedback_pmd_cmd"
    bl_label = "Feedback PMD Materials"
    
    filepath = bpy.props.StringProperty(subtype="FILE_PATH")
    
    def execute(self, context):
        # We must call it with 'INVOKE_DEFAULT'.
        bpy.ops.material.feedback_pmd('INVOKE_DEFAULT', filepath=self.filepath)
        return { 'FINISHED' }
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    @classmethod
    def add_menu_func(cls, _self, context):
        _self.layout.operator(cls.bl_idname)


class ApplyDeformForExportOperator(bpy.types.Operator):
    '''Apply Modifier & ShapeKey Deformation to Mesh Object'''
    bl_idname = "object.apply_deform_for_export"
    bl_label = "Apply Deform"

    @classmethod
    def poll(cls, context):
        if context.active_object is not None:
            if context.active_object.mode == 'OBJECT':
                return context.active_object.type == 'MESH'
        return False

    def __get_other_shapekeys(self, mesh):
        if mesh.shape_keys == None:
            return [ ]
        return [ s.name for s in mesh.shape_keys.key_blocks if s != mesh.shape_keys.reference_key ]

    def __get_shapekey_basis(self, mesh):
        if mesh.shape_keys == None:
            return None
        return mesh.shape_keys.reference_key.name
    
    def __activate_shapekey(self, obj, key_name):
        obj.show_only_shape_key = True
        obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find(key_name)
    
    def __create_base_obj(self, scene, obj, obj_name, key_name=None):
        if key_name:
            self.__activate_shapekey(obj, key_name)
        new_mesh = obj.to_mesh(scene, apply_modifiers=True, settings='PREVIEW')
        new_obj = bpy.data.objects.new(obj_name, new_mesh)
        if key_name:
            new_obj.shape_key_add(name=key_name, from_mix=True)
        # Copy VertexGroup settings
        for vg in obj.vertex_groups:
            new_obj.vertex_groups.new(vg.name)
        # Copy parenting setting
        new_obj.parent = obj.parent
        new_obj.matrix_parent_inverse = obj.matrix_parent_inverse
        # Copy transformation settings
        new_obj.location            = obj.location
        new_obj.rotation_axis_angle = obj.rotation_axis_angle
        new_obj.rotation_euler      = obj.rotation_euler
        new_obj.rotation_mode       = obj.rotation_mode
        #new_obj.rotation_quaternion = obj.rotation_quaternion
        new_obj.scale               = obj.scale
        return new_obj
    
    def __join_shapekey(self, scene, dst_obj, src_obj, src_key_name):
        self.__activate_shapekey(src_obj, src_key_name)
        mesh = src_obj.to_mesh(scene, apply_modifiers=True, settings='PREVIEW')
        try:
            new_key = dst_obj.shape_key_add(name=src_key_name, from_mix=False)
            for dv, sv in zip(new_key.data, mesh.vertices):
                dv.co = sv.co
        finally:
            bpy.data.meshes.remove(mesh)
    
    def do_apply(self, scene, obj, obj_name):
        basis_name  = self.__get_shapekey_basis(obj.data)
        shape_names = self.__get_other_shapekeys(obj.data)
        
        new_obj = self.__create_base_obj(scene, obj, obj_name, basis_name)
        for name in shape_names:
            self.__join_shapekey(scene, new_obj, obj, name)
        
        scene.objects.link(new_obj)
        bpy.context.scene.update()
        return new_obj

    def execute(self, context):
        obj = context.active_object
        scene = context.scene
        # Duplicate input object
        bpy.ops.object.duplicate()
        copied_obj = bpy.context.active_object
        try:
            # Apply deformation
            new_obj = self.do_apply(scene, copied_obj, obj.name)
        finally:
            scene.objects.unlink(copied_obj)
            bpy.data.objects.remove(copied_obj)
        # Activate new object
        bpy.ops.object.select_all(action='DESELECT')
        new_obj.select = True
        scene.objects.active = new_obj
        return {'FINISHED'}


class SCENE_PT_meshio(bpy.types.Panel):
    bl_label = "MeshIO"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    
    @classmethod
    def poll(cls, context):
        return context.scene != None
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        row = layout.row()
        if "PMD_EXTEND_CONFIG" in scene:
            row.prop(scene, '["PMD_EXTEND_CONFIG"]', text="Extend Config", icon='FILE')
        else:
            row.label(text='No Extend Config')
        row = layout.row()
        if export_extender.get_toon_mesh_object():
            row.label(text=('ToonMeshObject: ' + export_extender.get_toon_mesh_object().name))
        else:
            row.label(text='ToonMeshObject: None')


class MATERIAL_PT_meshio(bpy.types.Panel):
    bl_label = "MeshIO"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    
    def draw(self, context):
        layout = self.layout
        layout.label("Feedback Tools:")
        op = layout.row().operator("material.feedback_pmd_cmd")


def register():
    # NOTE: register_module() is unnecessary here. We call it from blender26-meshio.
    bpy.types.INFO_MT_file_import.append(PmdMaterialFeedbackCmdOperator.add_menu_func)

def unregister():
    bpy.types.INFO_MT_file_import.remove(PmdMaterialFeedbackCmdOperator.add_menu_func)

