#!/usr/bin/env python3
"""
This converts geological structure and geophysical data files into a format for displaying in a web browser
"""

import sys
import os
import glob
import argparse
import logging
from types import SimpleNamespace

from lib.file_processing import read_json_file
from lib.config_builder import ConfigBuilder
from converters.gocad2webasset import Gocad2WebAsset

CONVERT_COLLADA = True
''' Runs the collada2gltf program after creating COLLADA files
'''

DEBUG_LVL = logging.CRITICAL
''' Initialise debug level to minimal debugging
'''

# Set up debugging
LOGGER = logging.getLogger("conv_webasset")

# Create console handler
LOCAL_HANDLER = logging.StreamHandler(sys.stdout)

# Create formatter
LOCAL_FORMATTER = logging.Formatter('%(asctime)s -- %(name)s -- %(levelname)s - %(message)s')

# Add formatter to ch
LOCAL_HANDLER.setFormatter(LOCAL_FORMATTER)

# Add handler to LOGGER
LOGGER.addHandler(LOCAL_HANDLER)

#LOGGER.setLevel(logging.DEBUG)



def find(converter_obj, src_dir, dest_dir, config_build_obj):
    ''' Searches for 3rd party model files in all the subdirectories

    :param converter_obj: file converter object
    :param src_dir: directory in which to begin the search
    :param dest_dir: directory to store output
    :param config_build_obj: ConfigBuilder object
    '''
    LOGGER.debug("find(%s, %s)", src_dir, dest_dir)
    model_dict_list = []
    geoext_list = []
    walk_obj = os.walk(src_dir)
    for root, subfolders, files in walk_obj:
        done = False
        for file in files:
            name_str, fileext_str = os.path.splitext(file)
            for target_fileext_str in converter_obj.get_supported_exts():
                if fileext_str.lstrip('.').upper() == target_fileext_str:
                    find_and_process(converter_obj, root, dest_dir)
                    done = True
                    break
            if done:
                break


def find_and_process(converter_obj, src_dir, dest_dir):
    ''' Searches for files in local directory and processes them

    :param src_dir: source directory where there are 3rd party model files
    :param dest_dir: destination directory where output is written to
    :param ext_list: list of supported file extensions
    '''
    LOGGER.debug("find_and_process(%s, %s)", src_dir, dest_dir)
    for ext_str in converter_obj.get_supported_exts():
        wildcard_str = os.path.join(src_dir, "*."+ext_str.lower())
        file_list = glob.glob(wildcard_str)
        for filename_str in file_list:
            converter_obj.process(filename_str, dest_dir)

    # Convert all files from COLLADA to GLTF v2
    if CONVERT_COLLADA:
        collada2gltf.convert_dir(dest_dir)


def check_input_params(param_dict, param_file):
    """ Checks that the input parameter file has all the mandatory fields and
        that there are no duplicate labels

        :param param_dict: parameter file as a dict
        :param param_file: filename of parameter file (string)
    """
    # Check for 'ModelProperties'
    if 'ModelProperties' not in param_dict:
        LOGGER.error("Cannot find 'ModelProperties' key in JSON file: %s", param_file)
        sys.exit(1)

    # Check for 'GroupStructure'
    if 'GroupStructure' not in param_dict:
        LOGGER.error("Cannot find 'GroupStructure' key in JSON file: %s", param_file)
        sys.exit(1)

    # Check for duplicate group names
    group_names = param_dict['GroupStructure'].keys()
    if len(group_names) > len(set(group_names)):
        LOGGER.error("Cannot process JSON file: %s - found duplicate group names", param_file)
        sys.exit(1)

    # Check for duplicate labels
    for part_list in param_dict['GroupStructure'].values():
        display_name_set = set()
        filename_set = set()
        for part in part_list:
            if part["FileNameKey"] in filename_set:
                LOGGER.error("Cannot process JSON file {0}: duplicate FileNameKey {1}".format(param_file, part["FileNameKey"]))
                sys.exit(1)
            filename_set.add(part["FileNameKey"])
            if "display_name" in part["Insert"] and \
                                 part["Insert"]["display_name"] in display_name_set:
                LOGGER.error("Cannot process JSON file {0}: duplicate display_name {1}".format(param_file, part["Insert"]["display_name"]))
                sys.exit(1)
            display_name_set.add(part["Insert"]["display_name"])


def initialise_params(param_file):
    ''' Reads the input parameter file and returns a dict version of input params

    :param param_file: file name of input parameter file
    '''
    params_obj = SimpleNamespace()
    param_dict = read_json_file(param_file)
    check_input_params(param_dict, param_file)

    # Mandatory parameters
    for field_name in ['crs', 'name', 'init_cam_dist', 'modelUrlPath']:
        if field_name not in param_dict['ModelProperties']:
            LOGGER.error('Field "{0}" not in "ModelProperties" in JSON input param file {1}'.format(field_name, param_file))
            sys.exit(1)
        setattr(params_obj, field_name, param_dict['ModelProperties'][field_name])
    model_url_path = param_dict['ModelProperties']['modelUrlPath']

    # Optional parameter
    if 'proj4_defn' in param_dict['ModelProperties']:
        setattr(params_obj, 'proj4_defn', param_dict['ModelProperties']['proj4_defn'])

    # Optional Coordinate Offsets
    coord_offset = {}
    if 'CoordOffsets' in param_dict:
        for coord_offset_obj in param_dict['CoordOffsets']:
            coord_offset[coord_offset_obj['filename']] = tuple(coord_offset_obj['offset'])

    # Optional colour table files for VOXET file
    ct_file_dict = {}
    if 'VoxetColourTables' in param_dict:
        for ct_obj in param_dict['VoxetColourTables']:
            colour_table = ct_obj['colour_table']
            filename = ct_obj['filename']
            transp = ct_obj.get('render_transparent',[])
            ct_file_dict[filename] = (colour_table, transp)

    # Optional WMS services
    setattr(params_obj, 'wms_services', [])
    if 'WMSServices' in param_dict:
        for wms_svc in param_dict['WMSServices']:
            params_obj.wms_services.append(wms_svc)

    # Optional labels for sidebars
    setattr(params_obj, 'grp_struct_dict', {})
    if 'GroupStructure' in param_dict:
        for group_name, command_list in param_dict['GroupStructure'].items():
            for command in command_list:
                params_obj.grp_struct_dict[command["FileNameKey"]] = (group_name,
                                                                      command["Insert"])
    return params_obj, model_url_path, coord_offset, ct_file_dict



# MAIN PART OF PROGRAMME
if __name__ == "__main__":

    # Parse the arguments
    PARSER = argparse.ArgumentParser(description='Convert GOCAD files into geological model files')
    PARSER.add_argument('src', help='GOCAD source directory or source file',
                        metavar='GOCAD source dir/file')
    PARSER.add_argument('param_file', help='Input parameters in JSON format',
                        metavar='JSON input param file')
    PARSER.add_argument('-o', '--output_config', action='store', help='Output JSON config file',
                        default='output_config.json')
    PARSER.add_argument('-r', '--recursive', action='store_true',
                        help='Recursively search directories for files')
    PARSER.add_argument('-d', '--debug', action='store_true',
                        help='Print debug statements during execution')
    PARSER.add_argument('-x', '--nondefault_coords', action='store_true',
                        help='Do not stop if a file has a non-default GOCAD coordinate system')
    PARSER.add_argument('-f', '--output_folder', action='store',
                        help='Output folder for graphics files')
    PARSER.add_argument('-g', '--no_gltf', action='store_true',
                        help='Create COLLADA files, but do not convert to GLTF')
    ARGS = PARSER.parse_args()

    # If just want to create COLLADA files without converting them to GLTF
    if ARGS.no_gltf:
        CONVERT_COLLADA = False

    # Initialise output directory, default is source directory
    DEST_DIR = os.path.dirname(ARGS.src)
    if ARGS.output_folder is not None:
        if not os.path.isdir(ARGS.output_folder):
            print("Output folder", repr(ARGS.output_folder), "is not a directory", )
            sys.exit(1)
        DEST_DIR = ARGS.output_folder

    # Set debug level
    if ARGS.debug:
        DEBUG_LVL = logging.DEBUG
    else:
        DEBUG_LVL = logging.INFO

    # Read parameters & initialise converter
    params_obj, model_url_path, coord_offset, ct_file_dict = initialise_params(ARGS.param_file)
    converter = Gocad2WebAsset(DEBUG_LVL, params_obj, model_url_path, coord_offset, ct_file_dict, ARGS.nondefault_coords)

    # Process a directory of files
    if os.path.isdir(ARGS.src):

        # Recursively search subdirectories
        if ARGS.recursive:
            find(converter, ARGS.src, DEST_DIR, converter.config_build_obj)

        # Only search local directory
        else:
            find_and_process(converter, ARGS.src, DEST_DIR)

    # Process a single file
    elif os.path.isfile(ARGS.src):
        converter.process(ARGS.src, DEST_DIR)

        # Convert all files from COLLADA to GLTF v2
        if not converter.config_build_obj.has_output():
            print("Could not convert file", ARGS.src)
            sys.exit(1)
        if CONVERT_COLLADA:
            FILE_NAME, FILE_EXT = os.path.splitext(ARGS.src)
            collada2gltf.convert_file(os.path.join(DEST_DIR,
                                      os.path.basename(FILE_NAME) + ".dae"))

    else:
        print(ARGS.src, "does not exist")
        sys.exit(1)

    # Finally, create the config file
    if converter.config_build_obj.has_output():
        converter.config_build_obj.create_json_config(ARGS.output_config, DEST_DIR,
                                         converter.params)
