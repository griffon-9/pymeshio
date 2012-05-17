#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

import bpy

import traceback
import io
import math
import collections
from pprint import pprint
import json
import string
import datetime
import ast
import imp
import sys

# Import pymeshio constant definitions
if "bl" in locals():
    imp.reload(bl)
    imp.reload(pymeshio)
else:
    from . import bl
    from . import pymeshio

PYMESHIO_BASE_VERSION = "2.6.1"

# Check: Is meshutils available ?
def external_ops_enabled():
    return "meshutils_gr" in sys.modules

def open_file_safe(filename):
    file = None
    try:
        file = open(filename, "r", encoding="UTF-8")
    except Exception as e:
        traceback.print_exc()
        file = io.StringIO("")
    return file

def get_n_elements(iter, n):
    """イテレータの要素をn個ずつlistで返すジェネレータ"""
    while True:
        data = [ ]
        for i in range(n):
            data.append(next(iter))
        yield data

def cleanup_lines(io):
    """各行をstripしてさらに空行を除去するジェネレータ"""
    for line in (l.strip() for l in io):
        if len(line) > 0:
            yield line

def truncate_str_in_bytes(input_str, size_in_bytes, encoding="cp932"):
    """文字列を指定バイト数に収まるように末尾切り捨てする"""
    result = input_str
    while len(result.encode(encoding)) >= size_in_bytes:
        result = result[:-1]
    return result





def get_toon_mesh_object():
    return next(filter(lambda o: o.name.startswith(bl.TOON_TEXTURE_OBJECT), bpy.context.scene.objects), None)

def get_toon_material():
    toon_obj = get_toon_mesh_object()
    return toon_obj.data.materials[0] if (toon_obj and toon_obj.data and len(toon_obj.data.materials) > 0) else None

def create_edge_flag_func(obj):
    class EdgeFlagTestFunc:
        def __init__(self, obj):
            self.vg_index = -1
            for i, vg in enumerate(obj.vertex_groups):
                if vg.name == bl.MMD_EDGEFLAG_GROUP_NAME:
                    self.vg_index = i
                    break;
        def __call__(self, v):
            if any( ( g.group == self.vg_index for g in v.groups) ):
                return 1
            else:
                return 0
    return EdgeFlagTestFunc(obj)

class Math:
    @staticmethod
    def normalize(*values):
        total = math.fsum(values)
        return tuple((v / total if total > 0.0 else 0.0) for v in values)

class ExportInfo:
    def __init__(self):
        self._data = { "materials": [], }
    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        return None
    def as_string(self):
        return json.dumps(self._data, indent=2)
    @staticmethod
    def load():
        tmp = ExportInfo()
        if "PMD_EXPORT_INFO" in bpy.context.scene:
            text = bpy.data.texts[bpy.context.scene["PMD_EXPORT_INFO"]]
            tmp._data = json.loads(text.as_string())
        return tmp

class Context:
    __current = None
    
    def __init__(self, mode):
        self.mode = mode
        self.__exit_handler = [ ]
        self.export_info = ExportInfo()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        for func in self.__exit_handler:
            func()
        self.__exit_context(self)
    
    def __getattr__(self, name):
        return None
    
    def add_exit_handler(self, func):
        self.__exit_handler.append(func)
    
    @classmethod
    def init(cls, mode='pmd'):
        cls.__current = Context(mode)
        return cls.__current
    
    @classmethod
    def __exit_context(cls, ctx):
        if cls.__current is ctx:
            cls.__current = None
    
    @classmethod
    def current(cls):
        return cls.__current

class EnglishMap:
    englishmap = None
    
    class MapEditor:
        def __index_of(self, english_name):
            for i, name in enumerate((entry[0] for entry in self.__target)):
                if name == english_name:
                    return i
            raise IndexError("Not found: %s" % english_name)
        
        def __rename_tail(self, cmd_name):
            for i, entry in enumerate(self.__target):
                if entry[0].endswith("_L_t"):
                    self.__target[i] = (entry[0][:-4] + "_t_L",) + entry[1:]
                elif entry[0].endswith("_R_t"):
                    self.__target[i] = (entry[0][:-4] + "_t_R",) + entry[1:]
        
        def __append(self, cmd_name, mapping_list):
            for m in mapping_list:
                self.__target.append(tuple(m))
        
        def __insert_after(self, cmd_name, position, mapping_list):
            index = self.__index_of(position) + 1
            self.__target[index:index] = [ tuple(m) for m in mapping_list ]
        
        def __replace(self, cmd_name, mapping_list):
            for entry in mapping_list:
                index = self.__index_of(entry[0])
                self.__target[index] = entry
        
        def __init__(self, target):
            self.__target = target
            self.__cmd_table = {
                "rename_tail": self.__rename_tail,
                "append": self.__append,
                "insert_after": self.__insert_after,
                "replace": self.__replace,
            }
        
        def apply_cmds(self, cmd_list):
            for cmd in cmd_list:
                try:
                    if cmd[0] in self.__cmd_table:
                        self.__cmd_table[cmd[0]](*cmd)
                    else:
                        print(type(self), "Unknown Command:", cmd[0])
                except:
                    traceback.print_exc()
    
    @classmethod
    def init_once(cls):
        """ビルトインのenglishmapを複製して内部初期化する"""
        if cls.englishmap:
            return
        cls.englishmap = pymeshio.englishmap
        if "boneMapOrig" in dir(cls.englishmap):
            return
        cls.englishmap.boneMapOrig = cls.englishmap.boneMap[:]
        cls.englishmap.boneGroupMapOrig = cls.englishmap.boneGroupMap[:]
        cls.englishmap.skinMapOrig = cls.englishmap.skinMap[:]
    
    @classmethod
    def create_customized(cls):
        """カスタマイズを適用したenglishmapを生成する"""
        cls.init_once()
        conf = Config()
        cls.englishmap.boneMap = cls.englishmap.boneMapOrig[:]
        editor = cls.MapEditor(cls.englishmap.boneMap)
        editor.apply_cmds(conf.lookup("englishmap.bone", []))
        #print(cls.englishmap.boneMap)
        cls.englishmap.boneGroupMap = cls.englishmap.boneGroupMapOrig[:]
        editor = cls.MapEditor(cls.englishmap.boneGroupMap)
        editor.apply_cmds(conf.lookup("englishmap.bone_group", []))
        cls.englishmap.skinMap = cls.englishmap.skinMapOrig[:]
        editor = cls.MapEditor(cls.englishmap.skinMap)
        editor.apply_cmds(conf.lookup("englishmap.skin", []))

    class NamePair:
        __slots__ = [ 'name', 'english_name', 'bl_name' ]
        def __init__(self, name, eng, bl_name):
            self.name, self.english_name, self.bl_name = name, eng, bl_name

    class StrategyNone:
        def handle_names(self, nameMap, name, english_name):
            return EnglishMap.NamePair(name, english_name, name)
        def get_additional_data(self, nameMap, namepair, default):
            return next(( entry[2] for entry in nameMap
                if entry[1] == namepair.bl_name and len(entry) > 2 ), default)

    class StrategyBlenderEN:
        """出力する名前についてBlender側を英語名とみなす変換規則を適用する"""
        def handle_names(self, nameMap, name, english_name):
            j_name = next(( entry[1] for entry in nameMap if entry[0] == name ), name)
            return EnglishMap.NamePair(j_name, name, name)
        def get_additional_data(self, nameMap, namepair, default):
            return next(( entry[2] for entry in nameMap
                if entry[0] == namepair.bl_name and len(entry) > 2 ), default)

    @classmethod
    def __get_name_strategy(cls):
        ctx = Context.current()
        if ctx.name_strategy is None:
            conf_val = Config().lookup_ex("englishmap.strategy", None)
            if conf_val == "BLENDER_EN":
                ctx.name_strategy = cls.StrategyBlenderEN()
            else:
                ctx.name_strategy = cls.StrategyNone()
        return ctx.name_strategy

    @classmethod
    def handle_names(cls, name_type, name, english_name):
        """出力する名前について変換規則を設定に応じて変更する"""
        _maps = {
            'BONE': cls.englishmap.boneMap,
            'BONEGROUP': cls.englishmap.boneGroupMap,
            'MORPH': cls.englishmap.skinMap,
        }
        return cls.__get_name_strategy().handle_names(
                    _maps[name_type], name, english_name)

    @classmethod
    def get_additional_data(cls, name_type, namepair, default=None):
        _maps = {
            'BONE': cls.englishmap.boneMap,
            'BONEGROUP': cls.englishmap.boneGroupMap,
            'MORPH': cls.englishmap.skinMap,
        }
        return cls.__get_name_strategy().get_additional_data(
                    _maps[name_type], namepair, default)


class MeshSetup:
    @classmethod
    def __context(cls):
        ctx = Context.current()
        return ctx
    
    @classmethod
    def __create_edge_flag_func(cls, obj):
        class EdgeFlagTestFunc:
            def __init__(self, obj):
                self.mesh = obj.data
                self.vg_index = -1
                for i, vg in enumerate(obj.vertex_groups):
                    if vg.name == bl.MMD_EDGEFLAG_GROUP_NAME:
                        self.vg_index = i
                        break;
            def __call__(self, v_index):
                v = self.mesh.vertices[v_index]
                if any( ( g.group == self.vg_index for g in v.groups) ):
                    return 1
                else:
                    return 0
        return EdgeFlagTestFunc(obj)
    
    @classmethod
    def set_current_mesh_obj(cls, obj):
        """エッジ描画フラグ判定のための対象Meshを登録する"""
        ctx = cls.__context()
        ctx.edge_flag_func = cls.__create_edge_flag_func(obj) if obj else None
    
    @classmethod
    def get_edge_flag(cls, vertex_index):
        """エッジ描画フラグを判定して返す"""
        ctx = cls.__context()
        return ctx.edge_flag_func(vertex_index) if ctx.edge_flag_func else 0
    
    @classmethod
    def __complete_asymmetry_shapekeys(cls, obj, name_base, name_L, name_R):
        """ShapeKeyを左右分割して新しいShapeKeyを作成する"""
        if not external_ops_enabled():
            return
        key_blocks = obj.data.shape_keys.key_blocks
        if not name_base in key_blocks:
            return
        if name_L in key_blocks:
            return
        if name_R in key_blocks:
            return
        bpy.context.scene.objects.active = obj
        bpy.ops.object.split_shapekey_lr(target_name=name_base, left_name=name_L, right_name=name_R)
    
    @classmethod
    def autocomplete_shapekeys(cls, obj):
        if not obj.data.shape_keys:
            return
        cls.__complete_asymmetry_shapekeys(obj, "blink", "wink2_R", "wink2")
        cls.__complete_asymmetry_shapekeys(obj, "smile", "wink_R", "wink")
    
    @classmethod
    def transform_mesh(cls, mesh, matrix):
        """エクスポート用にMeshの頂点と全ShapeKeyを座標変換する"""
        mesh.transform(matrix)
        if not mesh.shape_keys:
            return
        # NOTE: MeshのtransformだけではShapeKeyのShapeKeyPointは座標変換されない？
        for key in mesh.shape_keys.key_blocks:
            for point in key.data:
                point.co = matrix * point.co
    
    @classmethod
    def duplicate_obj_for_export(cls, obj):
        """MeshオブジェクトをShapeKey有効な状態でModifierを適用しつつコピーする"""
        if not external_ops_enabled():
            return bl.object.duplicate(obj)
        bpy.ops.object.select_all(action = 'DESELECT')
        obj.select = True
        bpy.context.scene.objects.active = obj
        bpy.ops.object.apply_deform_special()
        output = bpy.context.active_object
        return output.data, output

class BoneDB:
    class BoneData:
        """Boneの情報を保持するクラス（Blender側への参照を保持するのは良くない）"""
        def __init__(self, name):
            self.name = name
            self.level = 0 # 変形階層
            self.parent = None # BoneData of parent
            self.has_children = False
            self.use_connect = True
            self.use_deform = True
            self.layer_visible = True # Layer which this bone exists in is visible.
    
    def __init__(self):
        self.name_list = []
        self.bone_map  = {}
    
    def get_data(self, name):
        if not name in self.bone_map:
            self.bone_map[name] = self.BoneData(name)
            self.name_list.append(name)
        return self.bone_map[name]
    
    def __scan_bones(self, parent, bones, level, pose):
        if parent:
            parent_data = self.bone_map[parent.name]
            parent_data.has_children = True
        else:
            parent_data = None
        # Recursive Scanning
        for b in bones:
            data = self.get_data(b.name)
            data.level = level
            data.parent = parent_data
            data.use_connect = b.use_connect
            data.use_deform = b.use_deform
            self.__scan_bones(b, self.sort_sibling_bones(b.children), level + 1, pose)
    def __scan_layers(self, armature):
        for b in armature.bones:
            data = self.get_data(b.name)
            data.layer_visible = any( (a and b) for a, b in zip(armature.layers, b.layers) )
    
    @classmethod
    def current(cls):
        ctx = Context.current()
        if not ctx.bone_db:
            ctx.bone_db = BoneDB()
        return ctx.bone_db
    
    @staticmethod
    def sort_sibling_bones(bones):
        """兄弟ボーンを重み付けしてソートする"""
        return sorted(bones, key=lambda b: len(b.children_recursive), reverse=True)
    
    @classmethod
    def index_by_name(cls, name):
        return cls.current().name_list.index(name)
    
    @classmethod
    def get_by_name(cls, name):
        return cls.current().bone_map[name]
    
    @classmethod
    def scan_armature(cls, obj):
        """Exportの準備のためにArmature Objectから情報を収集する"""
        db = cls.current()
        # parentなしBoneを選別する
        no_parents = [ b for b in obj.data.bones if not b.parent ]
        pose = obj.pose
        # Bone & Poseの解析
        db.__scan_bones(None, no_parents, 0, pose)
        # Armature Layerの解析
        db.__scan_layers(obj.data)


class BoneSetup:
    @classmethod
    def __context(cls):
        ctx = Context.current()
        if ctx.special_bones is None:
            ctx.special_bones = Config().lookup("bone.override", {})
            ctx.bone_strategy = Config().lookup_ex("bone.strategy", None)
        return ctx
    
    @classmethod
    def is_overridden(cls, bone_name):
        ctx = cls.__context()
        return bone_name in ctx.special_bones

    @classmethod
    def select_root_bones(cls, bone_list):
        """Armatureのボーンから親のないものを選別し、sortしてlistで返す"""
        return sorted( filter(lambda b: not b.parent, bone_list),
                        key=lambda b: len(b.children_recursive), reverse=True )

    @classmethod
    def sort_children(cls, bone_list):
        return sorted(bone_list,
                        key=lambda b: len(b.children_recursive), reverse=True )

    @classmethod
    def __handle_bone_compat(cls, bone_name, bone):
        val = pymeshio.englishmap.getUnicodeBoneName(bone_name)
        if val and len(val) > 2:
            bone.type = val[2]

    @classmethod
    def postprocess_bone(cls, bone_name, bone, index_func):
        ctx = cls.__context()
        if ctx.bone_strategy == 'PYMESHIO_1X_COMPAT':
            cls.__handle_bone_compat(bone_name, bone)
        if bone_name in ctx.special_bones:
            bone_param = ctx.special_bones[bone_name]
            if "type" in bone_param:
                bone.type = bone_param["type"]
            if "tail" in bone_param:
                bone.tail_index = index_func(bone_param["tail"])
            if "ik" in bone_param:
                if bone_param["ik"] is None:
                    bone.ik_index = 0xFFFF
                elif bone.type == 9:
                    bone.ik_index = bone_param["ik"]
                else:
                    bone.ik_index = index_func(bone_param["ik"])


class MaterialSetup:
    MATERIAL_SHINNESS="material_shinness"
    
    @classmethod
    def __context(cls):
        ctx = Context.current()
        if ctx.material_override is None:
            ctx.material_override = Config().lookup("material.override", {})
        if ctx.material_count is None:
            ctx.material_count = 0;
        return ctx
    
    @classmethod
    def postprocess_material(cls, material, bl_material):
        ctx = cls.__context()
        if bl_material.name in ctx.material_override:
            m_param = ctx.material_override[bl_material.name]
            if "diffuse" in m_param:
                material.diffuse_color.r, material.diffuse_color.g, \
                material.diffuse_color.b, material.alpha = \
                    tuple(m_param["diffuse"])
            if "shinness" in m_param:
                material.specular_factor = int(m_param["shinness"])
            if "specular" in m_param:
                material.specular_color.r, material.specular_color.g, material.specular_color.b = \
                    tuple(m_param["specular"])
            if "ambient" in m_param:
                material.ambient_color.r, material.ambient_color.g, material.ambient_color.b = \
                    tuple(m_param["ambient"])
            # TODO: Edge Flag
            if "toon" in m_param:
                material.toon_index = m_param["toon"]
        # Record export information
        ctx.export_info.materials.append({ "name": bl_material.name, "index": ctx.material_count })
        ctx.material_count += 1
    
    @classmethod
    def toon_index_for_material(cls, m):
        toonMeshObject = get_toon_mesh_object()
        if toonMeshObject is None:
            return 0
        toonMaterial = bl.mesh.getMaterial(bl.object.getData(toonMeshObject), 0)
        for m_tex in ( slot.texture for slot in m.texture_slots if slot is not None ):
            for i in range(10):
                if toonMaterial.texture_slots[i].texture == m_tex:
                    #print("  toon_index:", m.name, ">", i)
                    return i
        return 0
    
    @classmethod
    def specular_factor_for_material(cls, m):
        if cls.MATERIAL_SHINNESS in m:
            return int(m[cls.MATERIAL_SHINNESS])
        else:
            return 15

class RigidDefReader:
    
    def __init__(self, bone_index_func=None, bone_pos_func=None):
        self.boneName2Index = bone_index_func if bone_index_func else (lambda n: 0xFFFF)
        self.boneIndex2Pos = bone_pos_func if bone_pos_func else (lambda i: None)
        self.filepath = Config().lookup("physics.pmde_rigid", None)
    
    @classmethod
    def __read_entries(cls, filepath):
        with open_file_safe(filepath) as f:
            for elem in get_n_elements(cleanup_lines(f), 10):
                yield elem

    def create_rigids(self, constructor):
        """RigidBodyオブジェクトを作成してイテレータとして取得する"""
        if self.filepath is None:
            return
        for lines in self.__read_entries(bpy.path.abspath(self.filepath)):
            try:
                rigid = constructor(lines[0])
                # 関連ボーン
                rigid.bone_index = self.boneName2Index(lines[1])
                if rigid.bone_index < 0:
                    print("WARNING: Unknown bone name for rigid :", lines[0])
                # 剛体タイプ
                rigid.mode = int(lines[2])
                # グループ
                rigid.collision_group = int(lines[3])
                # 非衝突グループ
                target_tmp = 0
                if lines[4] != "[Null]":
                    for i in (int(s) for s in lines[4].strip("( )").split()):
                        target_tmp = target_tmp | (1 << (i - 1))
                #rigid.no_collision_group = 0xFFFF - target_tmp
                rigid.no_collision_group = -(target_tmp + 1) # pymeshioのバグ？ signed shortで処理する
                # 形状
                rigid.shape_type = int(lines[5])
                # 剛体サイズ
                rigid.shape_size.x, rigid.shape_size.y, rigid.shape_size.z = \
                    (float(s) for s in lines[6].split(","))
                # 剛体座標
                rigid.shape_position.x, rigid.shape_position.y, rigid.shape_position.z = \
                    (float(s) for s in lines[7].split(","))
                # 剛体座標の補正（ボーン座標からの相対位置へ変換）
                if self.boneIndex2Pos(rigid.bone_index):
                    _bone_pos = self.boneIndex2Pos(rigid.bone_index)
                    rigid.shape_position.x -= _bone_pos.x
                    rigid.shape_position.y -= _bone_pos.y
                    rigid.shape_position.z -= _bone_pos.z
                # 剛体回転
                rigid.shape_rotation.x, rigid.shape_rotation.y, rigid.shape_rotation.z = \
                    (math.radians(float(s)) for s in lines[8].split(","))
                # 物理演算パラメータ
                rigid.mass, rigid.linear_damping, rigid.angular_damping, rigid.restitution, rigid.friction = \
                    (float(s) for s in lines[9].split(","))
                yield rigid
            except ValueError:
                traceback.print_exc()


class JointDefReader:
    
    def __init__(self, rigidNameMap={}):
        self.rigidNameMap = rigidNameMap
        self.filepath = Config().lookup("physics.pmde_joint", None)
    
    @classmethod
    def __read_entries(cls, filepath):
        with open_file_safe(filepath) as f:
            for elem in get_n_elements(cleanup_lines(f), 11):
                yield elem

    def create_joints(self, constructor):
        """Constraintオブジェクトを作成してイテレータとして取得する"""
        if self.filepath is None:
            return
        for lines in self.__read_entries(bpy.path.abspath(self.filepath)):
            try:
                joint = constructor(lines[0])
                # 接続剛体A
                joint.rigidbody_index_a = self.rigidNameMap.get(lines[1], 0xFFFF)
                # 接続剛体B
                joint.rigidbody_index_b = self.rigidNameMap.get(lines[2], 0xFFFF)
                # ジョイント位置
                joint.position.x, joint.position.y, joint.position.z = \
                    (float(s) for s in lines[3].split(","))
                # ジョイント回転
                joint.rotation.x, joint.rotation.y, joint.rotation.z = \
                    (math.radians(float(s)) for s in lines[4].split(","))
                # 移動制限Min
                joint.translation_limit_min.x, joint.translation_limit_min.y, joint.translation_limit_min.z = \
                    (float(s) for s in lines[5].split(","))
                # 移動制限Max
                joint.translation_limit_max.x, joint.translation_limit_max.y, joint.translation_limit_max.z = \
                    (float(s) for s in lines[6].split(","))
                # 回転制限Min
                joint.rotation_limit_min.x, joint.rotation_limit_min.y, joint.rotation_limit_min.z = \
                    (math.radians(float(s)) for s in lines[7].split(","))
                # 回転制限Max
                joint.rotation_limit_max.x, joint.rotation_limit_max.y, joint.rotation_limit_max.z = \
                    (math.radians(float(s)) for s in lines[8].split(","))
                # ばね移動
                joint.spring_constant_translation.x, joint.spring_constant_translation.y, joint.spring_constant_translation.z = \
                    (float(s) for s in lines[9].split(","))
                # ばね回転
                joint.spring_constant_rotation.x, joint.spring_constant_rotation.y, joint.spring_constant_rotation.z = \
                    (float(s) for s in lines[10].split(","))
                yield joint
            except ValueError:
                traceback.print_exc()

class Config(collections.UserDict):
    __config = None
    
    @classmethod
    def __load_config(cls, filepath):
        with open_file_safe(filepath) as f:
            try:
                if filepath.endswith(".json"):
                    return json.load(f)
                else:
                    return ast.literal_eval(f.read())
            except:
                traceback.print_exc()
                return { }
    
    @classmethod
    def __find_configpath(cls):
        if "PMD_EXTEND_CONFIG" in bpy.context.scene:
            return bpy.path.abspath(bpy.context.scene["PMD_EXTEND_CONFIG"])
        return None
    
    @classmethod
    def config(cls, filepath=None):
        if cls.__config is None:
            filepath = cls.__find_configpath() if filepath is None else filepath
            cls.__config = cls.__load_config(filepath) if filepath is not None else { }
            if Context.current() is not None:
                Context.current().add_exit_handler(cls.clear)
        return cls.__config
    
    @classmethod
    def clear(cls):
        """キャッシュしている読み込み済みのデータを破棄する"""
        cls.__config = None
    
    def __init__(self, filepath=None):
        super().__init__(self.config(filepath))
    
    def lookup(self, key, default=None):
        """ドット区切りのキーに基づいてディクショナリの階層を辿って値を返す"""
        result = self
        try:
            for k in key.split("."):
                result = result[k]
            return result
        except KeyError:
            return default
    
    def lookup_ex(self, key, default=None):
        mode = Context.current().mode
        value = self.lookup(key, default)
        if isinstance(value, dict) and (mode in value):
            value = value[mode]
        return value

class ModelSetup:
    @classmethod
    def __get_mapping(cls):
        ctx = Context.current()
        if ctx.__mapping is None:
            ctx.__mapping = {
                "bl_version": ("%d.%d.%d" % bpy.app.version) + bpy.app.version_char,
                "bl_revision": bpy.app.build_revision.decode("UTF-8"),
                "mode": Context.current().mode,
                "date": datetime.datetime.now().strftime("%Y/%m/%d %H:%M"),
                "pymeshio_version": PYMESHIO_BASE_VERSION,
            }
        return ctx.__mapping

    @classmethod
    def __get_str(cls, conf, key, multiline=False):
        if isinstance(conf[key], list):
            _str = "\r\n".join(conf[key]) if multiline else conf[key][0]
        else:
            _str = conf[key]
        if conf.get("template", True) :
            _str = string.Template(_str).safe_substitute(cls.__get_mapping())
        return _str

    @classmethod
    def setattr_by_conf(cls, model, attr_name, key, conf, multiline, str_func = lambda x: x):
        if key in conf:
            val = cls.__get_str(conf, key, multiline)
            setattr(model, attr_name, str_func(val))

class PmdExporterSetup:
    @classmethod
    def setupModelNames(cls, model):
        conf = Config().get("pmd", None)
        if conf is None:
            conf = Config().get("model", {})
        
        _name_func    = lambda s: truncate_str_in_bytes(s, 20).encode("cp932")
        _comment_func = lambda s: truncate_str_in_bytes(s, 256).encode("cp932")
        
        ModelSetup.setattr_by_conf(model, "name", "name", conf, False, _name_func)
        ModelSetup.setattr_by_conf(model, "comment", "comment", conf, True, _comment_func)
        ModelSetup.setattr_by_conf(model, "english_name", "e_name", conf, False, _name_func)
        ModelSetup.setattr_by_conf(model, "english_comment", "e_comment", conf, True, _comment_func)

    @classmethod
    def store_export_info(cls):
        if "PMD_EXPORT_INFO" in bpy.context.scene:
            text_name = bpy.context.scene["PMD_EXPORT_INFO"]
        else:
            text_name = "PMD_LAST_EXPORT"
        if text_name in bpy.data.texts:
            text = bpy.data.texts[text_name]
        else:
            text = bpy.data.texts.new(text_name)
        bpy.context.scene["PMD_EXPORT_INFO"] = text.name
        text.from_string(Context.current().export_info.as_string())

class PmxExporterSetup:
    @classmethod
    def setupModelNames(cls, model):
        conf = Config().get("pmx", None)
        if conf is None:
            conf = Config().get("model", {})
        ModelSetup.setattr_by_conf(model, "name", "name", conf, False)
        ModelSetup.setattr_by_conf(model, "comment", "comment", conf, True)
        ModelSetup.setattr_by_conf(model, "english_name", "e_name", conf, False)
        ModelSetup.setattr_by_conf(model, "english_comment", "e_comment", conf, True)

# DEBUG
print("INFO: export_extender loaded.")


