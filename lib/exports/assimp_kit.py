import sys
import os
import logging
import ctypes
from ctypes import POINTER
from pyassimp import *

from exports.geometry_gen import colour_borehole_gen

import exports.print_assimp as pa
from exports.bh_utils import make_borehole_label

from db.style.false_colour import calculate_false_colour_num, make_false_colour_tup

class ASSIMP_KIT:
    ''' Class used to output export geometries to assimp lib
    '''

    def __init__(self, debug_level):
        ''' Initialise class

        :param debug_level: debug level taken from python's 'logging' module
        '''
        # Set up logging, use an attribute of class name so it is only called once
        if not hasattr(ASSIMP_KIT, 'logger'):
            ASSIMP_KIT.logger = logging.getLogger(__name__)

            # Create console handler
            handler = logging.StreamHandler(sys.stdout)

            # Create formatter
            formatter = logging.Formatter('%(asctime)s -- %(name)s -- %(levelname)s - %(message)s')

            # Add formatter to ch
            handler.setFormatter(formatter)

            # Add handler to logger and set level
            ASSIMP_KIT.logger.addHandler(handler)

        ASSIMP_KIT.logger.setLevel(debug_level)
        self.logger = ASSIMP_KIT.logger


    def write_borehole(self, bv, borehole_name, colour_info_dict, height_reso, dest_dir='', file_name='', file_ext='.gltf', export_type="gltf2", ):
        ''' Write out a file or blob of a borehole stick
            if 'dest_dir' and 'file_name' are supplied then writes a file and returns True/False
            else returns a pointer to a 'structs.ExportDataBlob' object

        :param bv: base vertex, position of the object within the model [x,y,z]
        :param borehole_name: name of borehole
        :param colour_info_dict: dict of colour info; key - depth, float, val - { 'colour' : (R,B,G,A), 'classText' : mineral name }, where R,G,B,A are floats
        :param height_reso: height resolution for colour info dict
        :param dest_dir: optional destination directory, where file is written
        :param file_name: optional filename of file, without extension
        :param file_ext: optional extension of file, defaults to '.gltf'
        :param export_type: optional export type for assimp API, defaults to 'gltf2'
        '''
        self.logger.debug(" write_borehole(%s, %s, %s, %s, colour_info_dict = %s)", bv, repr(dest_dir), repr(file_name), repr(borehole_name), repr(colour_info_dict), ")")

        sc = structs.Scene()
        sc.mMetadata = None
        sc.mPrivate = 0

        bh_size = len(colour_info_dict)

        # Set up meshes
        mesh_p_arr = (POINTER(structs.Mesh) * bh_size)()
        mesh_arr_pp = ctypes.cast(mesh_p_arr, POINTER(POINTER(structs.Mesh))) 
        sc.mMeshes = mesh_arr_pp
        sc.mNumMeshes = bh_size
        self.make_nodes(sc, b'root_node', b'child_node', bh_size)

        # Set up materials
        mat_p_arr = (POINTER(structs.Material) * bh_size)()
        mat_arr_pp = ctypes.cast(mat_p_arr, POINTER(POINTER(structs.Material)))
        sc.mMaterials = mat_arr_pp
        sc.mNumMaterials = bh_size

        for vert_list, indices, colour_idx, depth, colour_info, mesh_name in colour_borehole_gen(bv, borehole_name, colour_info_dict, height_reso):
            mesh_obj = self.make_a_mesh(mesh_name, indices, colour_idx)
            mesh_p_arr[colour_idx] = ctypes.pointer(mesh_obj)
            self.add_vertices_to_mesh(mesh_obj, vert_list)
            mat_obj = self.make_material(colour_info['colour'])
            mat_p_arr[colour_idx] = ctypes.pointer(mat_obj)

        #pa.print_scene(sc)
        #sys.stdout.flush()
        if dest_dir!='' and file_name !='':
            self.logger.info("Writing GLTF: %s", file_name+file_ext)
            export(sc, os.path.join(dest_dir, file_name+file_ext), export_type)
            self.logger.info(" DONE.")
            sys.stdout.flush()
            return True
        else:
            exp_blob = export_blob(sc, export_type, processing = None)
            #pa.print_blob(exp_blob)
            return exp_blob


    def make_empty_node(self, node_name):
        ''' Makes an empty node with a supplied name
        :param node_name: name of node to be created
        :returns: pyassimp 'Node' object
        '''
        n = structs.Node()
        n.mName.data = node_name
        n.mName.length = len(node_name)
        n.mTransformation = structs.Matrix4x4(1.0, 0.0, 0.0, 0.0,  0.0, 1.0, 0.0, 0.0,  0.0, 0.0, 1.0, 0.0,  0.0, 0.0, 0.0, 1.0)
        n.mParent = None
        n.mNumChildren = 0
        n.mChildren = None
        n.mNumMeshes = 0
        n.mMeshes = None
        n.mMetadata = None
        return n
       

    def make_nodes(self, scene, root_node_name, child_node_name, num_meshes):
        ''' Make the scene's root node and a child node

        :param s: pyassimp 'Scene' object
        :param root_node_name: bytes object, name of root node
        :param child_node_name: bytes object, name of child of root node
        '''
        # Make a root node
        parent_n = self.make_empty_node(root_node_name)
        parent_n.mNumChildren = 1
   
        # Make a child node
        child_n = self.make_empty_node(child_node_name)
        child_n.mParent = ctypes.pointer(parent_n)

        # Integer index to meshes
        mesh_idx_arr = (ctypes.c_uint * num_meshes)()
        for i in range(num_meshes):
            mesh_idx_arr[i] = i
        child_n.mMeshes = ctypes.cast(ctypes.pointer(mesh_idx_arr), POINTER(ctypes.c_uint))
        child_n.mNumMeshes = num_meshes

        ch_n_p = ctypes.pointer(child_n)
        ch_n_pp = ctypes.pointer(ch_n_p)
        parent_n.mChildren  = ch_n_pp
        scene.mRootNode = ctypes.pointer(parent_n)
    

    def make_a_mesh(self, mesh_name, index_list, material_index):
        ''' Creates a mesh object

        :param mesh_name: name of mesh object, bytes object
        :param index_list: list of integers, indexes into a vertex list
        :param material_index: index into scene's array of materials
        :returns: pyassimp 'Mesh' object
        '''
        m = structs.Mesh()
        num_faces = len(index_list)//3

        f_arr = (structs.Face * num_faces)()
        m.mFaces = ctypes.cast(f_arr, POINTER(structs.Face))
        m.mNumFaces = num_faces
        m.mPrimitiveTypes = 4  # Triangle
        m.mName.length = len(mesh_name)
        m.mName.data = mesh_name
        m.mMaterialIndex = material_index

        for f_idx, i_idx  in enumerate(range(0, len(index_list), 3)):
            i_arr = (ctypes.c_uint * 3)()
            i_arr[0] = index_list[i_idx]
            i_arr[1] = index_list[1+i_idx]
            i_arr[2] = index_list[2+i_idx]
            i_arr_p = ctypes.cast(i_arr, POINTER(ctypes.c_uint))
            f_arr[f_idx].mIndices = i_arr_p
            f_arr[f_idx].mNumIndices = 3
        return m


    def add_vertices_to_mesh(self, mesh, vertex_list):
        ''' Adds the vertices to a mesh

        :param mesh: pyassimp 'Mesh' object
        :param vertex_list: list of floats, (x,y,z) coords of vertices
        '''
        num_vertices = len(vertex_list)//3
        v_arr = (structs.Vector3D * num_vertices)()
        v_arr_p = ctypes.cast(v_arr, POINTER(structs.Vector3D))
        mesh.mVertices = v_arr_p
        mesh.mNumVertices = num_vertices
        for varr_idx, v_idx in enumerate(range(0, len(vertex_list), 3)):
            v_arr[varr_idx] = structs.Vector3D(vertex_list[v_idx], vertex_list[v_idx+1], vertex_list[v_idx+2])


    def make_colour(self, key, r,g,b,a):
        ''' Makes a pyassimp 'MaterialProperty' object for colour

        :param key: bytes object with name of key
        :param r,g,b,a: floating point values of RGBA colours
        '''
        p = structs.MaterialProperty()
        p.mSemantic = 0
        p.mIndex = 0
        p.mType = 1
        p.mDataLength = 16
        rgba_type = (ctypes.c_float * 4)
        col = rgba_type(r, g, b, a) 
        p.mData = ctypes.cast(col, POINTER(ctypes.c_char))
        p.mKey = structs.String(len(key),key) # b'$clr.diffuse'
        return p
        

    def make_material(self, diffuse_colour):
        ''' Makes a material object with a certain diffuse colour
        :param diffuse_colour: tuple of floating point values (R,G,B,A)
        :returns pyassimp 'Material' object
        '''
        m = structs.Material()
        m.mNumProperties = 1
        m.mNumAllocated = 1
        p = self.make_colour(b'$clr.diffuse', *diffuse_colour)
        pp = ctypes.pointer(p)
        ppp = ctypes.pointer(pp)
        m.mProperties = ppp
        return m

#  END OF ASSIMP_KIT CLASS
