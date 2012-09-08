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
import mathutils

import math
import re


class ChainItem:
    def __init__(self, chain_id, order, bone):
        self.chain_id = chain_id
        self.order = order
        self.name = bone.name
        self.parent_name = bone.parent.name
        self.head = None
        self.tail = None
        self.z_axis = None
    
    def __str__(self):
        return "<ChainItem : %s >" % (self.name)

class BoneChain:
    def __init__(self, chain_id):
        self.id = chain_id
        self.items = [ ]

    def add(self, order, bone, matrix):
        item = ChainItem(self.id, order, bone)
        # MMDの座標系へ変換を試みる
        item.euler = (bone.matrix).to_euler("XYZ")
        item.head = (matrix * bone.head).to_3d().xzy
        item.tail = (matrix * bone.tail).to_3d().xzy
        item.z_axis = bone.z_axis.xzy
        self.items.append(item)

    def validate(self):
        self.items.sort(key=lambda i: int(i.order))
    
    def show_names(self):
        print( *self.items )

class SkirtPhysicsGenerator:
    """スカート等の物理演算設定を生成する"""
    def __init__(self, config):
        self.config = config
        self.chains = { }
        self.boneName2Index = (lambda n: 0xFFFF)
        self.rigidName2Index = (lambda n: 0xFFFF)

    def setup(self, obj, armature, matrix):
        prefix = self.config.get("prefix", "SK")
        regex = re.compile(r'^@' + prefix + r'_(\d+)_(\d+)(_[LR])?')
        
        bpy.context.scene.objects.active = obj
        # EDITモードからの情報が必要
        bpy.ops.object.mode_set(mode='EDIT')
        for bone in armature.edit_bones:
            m = regex.match(bone.name)
            if not m:
                continue
            chain_id   = m.group(1) + (m.group(3) if m.group(3) else "" )
            item_order = m.group(2)
            if chain_id not in self.chains:
                self.chains[chain_id] = BoneChain(chain_id)
            self.chains[chain_id].add(item_order, bone, matrix)
        for chain in self.chains.values():
            chain.validate()
        bpy.ops.object.mode_set(mode='OBJECT')
        
        for k, c in self.chains.items():
            print("<", k, ">")
            c.show_names()
    
    @staticmethod
    def __distance(v1, v2):
        return math.sqrt( ((v2.x - v1.x) ** 2) + ((v2.y - v1.y) ** 2) + ((v2.z - v1.z) ** 2) )
    
    def __setup_rigid(self, rigid, item):
        # 関連ボーン
        rigid.bone_index = self.boneName2Index(item.name)
        if rigid.bone_index < 0:
            print("WARNING: Unknown bone name for rigid :", lines[0])
        # 剛体タイプ
        rigid.mode = 2 # 物理演算ボーン位置合わせ
        # グループ
        group = self.config.get("group", 3) # デフォルト値(グループ3)
        rigid.collision_group = group - 1
        # 非衝突グループ
        target_tmp = (1 << (group - 1)) # 自分と同じグループとは非衝突
        #rigid.no_collision_group = 0xFFFF - target_tmp
        rigid.no_collision_group = -(target_tmp + 1) # pymeshioのバグ？ signed shortで処理する
        # 形状
        rigid.shape_type = 1 # 箱（暫定）
        # 剛体サイズ
        bone_length = self.__distance(item.tail, item.head) / 2.0 # ボーンの長さ
        # 剛体サイズの単位はおそらくメッシュとは２倍違う？
        # Blender上でのボーンのZ軸に基づいて剛体のY軸が設定されているはず
        rigid.shape_size.x = bone_length * self.config.get("w_ratio", 1.2)
        rigid.shape_size.y = self.config.get("thick", 0.1)
        rigid.shape_size.z = bone_length * self.config.get("h_ratio", 0.8)
        # 剛体座標
        mid_point = (item.head + item.tail) / 2.0 # ボーンの中点
        rigid.shape_position.x = mid_point.x
        rigid.shape_position.y = mid_point.y
        rigid.shape_position.z = mid_point.z
        # NOTE: PMD出力時は剛体座標をボーン座標からの相対位置へ変換する必要があるが未実装
        # 剛体回転
        euler = item.euler
        rigid.shape_rotation.x = -euler.x
        rigid.shape_rotation.y = -euler.z
        rigid.shape_rotation.z = -euler.y
        # 物理演算パラメータ
        #_param = rigid.param if Context.current().mode == 'pmx' else rigid
        _param = rigid.param
        _param.mass = 0.1
        _param.linear_damping = 0.99
        _param.angular_damping = 0.99
        _param.restitution = 0.0
        _param.friction = 0.5

    def generate_rigids(self, constructor, bone_index_func):
        """剛体を生成してイテレートする"""
        self.boneName2Index = bone_index_func
        
        for chain in self.chains.values():
            for item in chain.items:
                rigid = constructor(item.name)
                try:
                    self.__setup_rigid(rigid, item)
                    yield rigid
                except ValueError:
                    traceback.print_exc()
    
    def __setup_chain_joint(self, joint, item):
        # 接続剛体A
        joint.rigidbody_index_a = self.rigidName2Index(item.parent_name)
        # 接続剛体B
        joint.rigidbody_index_b = self.rigidName2Index(item.name)
        # ジョイント位置
        joint.position.x = item.head.x
        joint.position.y = item.head.y
        joint.position.z = item.head.z
        # ジョイント回転
        y_rot = mathutils.Vector((0.0, 1.0)).angle_signed(item.z_axis.xz)
        joint.rotation.x, joint.rotation.y, joint.rotation.z = \
            ( 0.0, y_rot, 0.0 )
        # 移動制限Min
        joint.translation_limit_min.x, joint.translation_limit_min.y, joint.translation_limit_min.z = \
            ( 0.0, 0.0, 0.0 )
        # 移動制限Max
        joint.translation_limit_max.x, joint.translation_limit_max.y, joint.translation_limit_max.z = \
            ( 0.0, 0.0, 0.0 )
        # 回転制限Min
        joint.rotation_limit_min.x, joint.rotation_limit_min.y, joint.rotation_limit_min.z = \
            ( math.radians(d) for d in ( -40.0, 0.0, -20.0 ) )
        # 回転制限Max
        joint.rotation_limit_max.x, joint.rotation_limit_max.y, joint.rotation_limit_max.z = \
            ( math.radians(d) for d in ( 40.0, 0.0, 20.0 ) )
        # ばね移動
        joint.spring_constant_translation.x, joint.spring_constant_translation.y, joint.spring_constant_translation.z = \
            ( 0.0, 0.0, 0.0 )
        # ばね回転
        joint.spring_constant_rotation.x, joint.spring_constant_rotation.y, joint.spring_constant_rotation.z = \
            ( 0.0, 0.0, 0.0 )

    def __setup_bridge_joint(self, joint, item_a, item_b):
        # 接続剛体A
        joint.rigidbody_index_a = self.rigidName2Index(item_a.name)
        # 接続剛体B
        joint.rigidbody_index_b = self.rigidName2Index(item_b.name)
        # ジョイント位置
        # NOTE: ボーンの中間を計算（暫定）
        pos = (item_a.head + item_a.tail + item_b.head + item_b.tail) / 4.0
        joint.position.x = pos.x
        joint.position.y = pos.y
        joint.position.z = pos.z
        # ジョイント回転
        y_rot = mathutils.Vector((0.0, 1.0)).angle_signed( (item_a.z_axis.xz + item_b.z_axis.xz) )
        joint.rotation.x, joint.rotation.y, joint.rotation.z = \
            ( 0.0, y_rot, 0.0 )
        # 移動制限Min
        joint.translation_limit_min.x, joint.translation_limit_min.y, joint.translation_limit_min.z = \
            ( -1.0, -1.0, -1.0 )
        # 移動制限Max
        joint.translation_limit_max.x, joint.translation_limit_max.y, joint.translation_limit_max.z = \
            ( 1.0, 1.0, 1.0 )
        # 回転制限Min
        joint.rotation_limit_min.x, joint.rotation_limit_min.y, joint.rotation_limit_min.z = \
            ( math.radians(d) for d in ( -60.0, -30.0, -30.0 ) )
        # 回転制限Max
        joint.rotation_limit_max.x, joint.rotation_limit_max.y, joint.rotation_limit_max.z = \
            ( math.radians(d) for d in ( 60.0, 30.0, 30.0 ) )
        # ばね移動
        joint.spring_constant_translation.x, joint.spring_constant_translation.y, joint.spring_constant_translation.z = \
            ( 0.0, 0.0, 0.0 )
        # ばね回転
        joint.spring_constant_rotation.x, joint.spring_constant_rotation.y, joint.spring_constant_rotation.z = \
            ( 0.0, 0.0, 0.0 )

    def generate_joints(self, constructor, rigid_index_func):
        """ジョイントを生成してイテレートする"""
        self.rigidName2Index = rigid_index_func
        
        for chain in self.chains.values():
            for item in chain.items:
                # NOTE: ボーン自身の親との間にジョイントを作成する
                joint = constructor(item.name)
                try:
                    self.__setup_chain_joint(joint, item)
                    yield joint
                except ValueError:
                    traceback.print_exc()
        # NOTE: 横方向につなぐジョイントの生成も必要
        bridge_id_list = self.config.get("bridge", [])
        for id_a, id_b in bridge_id_list:
            chain_a = self.chains[id_a]
            chain_b = self.chains[id_b]
            for item_a, item_b in zip(chain_a.items, chain_b.items):
                joint = constructor("%s#%s" % (item_a.name, item_b.name))
                try:
                    self.__setup_bridge_joint(joint, item_a, item_b)
                    yield joint
                except ValueError:
                    traceback.print_exc()


