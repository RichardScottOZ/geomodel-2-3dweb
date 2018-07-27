import numpy
import sys
import os
import struct
from collections import namedtuple
from collections import OrderedDict
import logging
import traceback

from model_geometries import MODEL_GEOMETRIES

class PROPS:
    ''' This class holds GOCAD properties
        e.g. information about binary files (PROP_FILE)
             information attached to XYZ points (PATOM, PVRTX)
    '''

    def __init__(self, class_name):

        self.file_name = ""
        ''' Name of binary file associated with GOCAD file
        '''
       
        self.data_sz = 0 
        ''' Number of bytes in floating point number in binary file
        '''

        self.data_type = "f"
        ''' Type of data in binary file e.g. 'h' - short int, 'f' = float
        '''

        self.signed_int = False
        ''' Is True iff binary data is a signed integer else False
        '''

        self.data = {}
        ''' Property data collected from binary file, stored as a 3d numpy array.
            or property data attached to XYZ points (index is XYZ coordinate)
        '''

        self.data_stats = {}
        ''' Property data statistics: min & max
        '''

        self.colour_map = {}
        ''' If colour map was specified, then it is stored here
        '''

        self.colourmap_name = ""
        ''' Name of colour map
        '''

        self.class_name = class_name
        ''' Property class names
        '''

        self.no_data_marker = None
        ''' Value representing 'no data' values
        '''

    
    def __repr__(self):
        ''' A print friendly representation
        '''
        return "self = {:}\n".format(hex(id(self))) + \
               "file_name = {:}\n".format(repr(self.file_name)) + \
               "data_sz = {:d}\n".format(self.data_sz) + \
               "data_type = {:}\n".format(repr(self.data_type)) + \
               "signed_int = {:}\n".format(self.signed_int) + \
               "data = {:}\n".format(repr(self.data)) + \
               "data_stats = {:}\n".format(repr(self.data_stats)) + \
               "colour_map = {:}\n".format(repr(self.colour_map)) + \
               "colourmap_name = {:}\n".format(repr(self.colourmap_name)) + \
               "class_name = {:}\n".format(repr(self.class_name)) + \
               "no_data_marker = {:}\n".format(repr(self.no_data_marker))

    def make_numpy_dtype(self):
        ''' Returns a string that can be passed to 'numpy' to read a binary file
        '''
        # Prepare 'numpy' binary float integer signed/unsigned data types, always big-endian
        if self.data_type == 'h' or self.data_type == 'b':
            if not self.signed_int:
                return numpy.dtype('>'+self.data_type.upper())
            else:
                return numpy.dtype('>'+self.data_type)
        return numpy.dtype('>'+self.data_type+str(self.data_sz))



class GOCAD_VESSEL(MODEL_GEOMETRIES):
    ''' Class used to read GOCAD files and store their details
    '''

    GOCAD_HEADERS = {
                 'TS':['GOCAD TSURF 1'],
                 'VS':['GOCAD VSET 1'],
                 'PL':['GOCAD PLINE 1'],
                 'GP':['GOCAD HETEROGENEOUSGROUP 1', 'GOCAD HOMOGENEOUSGROUP 1'],
                 'VO':['GOCAD VOXET 1'],
    }
    ''' Constant assigns possible headers to each flename extension
    '''

    SUPPORTED_EXTS = [
                   'TS',
                   'VS',
                    'PL',
                    'GP',
                    'VO',
    ]
    ''' List of file extensions to search for
    '''


    COORD_OFFSETS = { 'FROM_SHAPE' : (535100.0, 0.0, 0.0) }
    ''' Coordinate offsets, when file contains a coordinate system  that is not "DEFAULT" 
        The named coordinate system and (X,Y,Z) offset will apply
    '''


    STOP_ON_EXC = True 
    ''' Stop upon exception, regardless of debug level
    '''


    def __init__(self, debug_level, base_xyz=(0.0, 0.0, 0.0), group_name="", nondefault_coords=False, stop_on_exc=True):
        ''' Initialise class
            debug_level - debug level taken from 'logging' module e.g. logging.DEBUG
            base_xyz - optional (x,y,z) floating point tuple, base_xyz is added to all coordinates
                       before they are output, default is (0.0, 0.0, 0.0)
            group_name - optional string, name of group of this gocad file is within a group, default is ""
            nondefault_coords - optional flag, supports non-default coordinates, default is False
        '''
        super().__init__()
        # Set up logging, use an attribute of class name so it is only called once
        if not hasattr(GOCAD_VESSEL, 'logger'):
            GOCAD_VESSEL.logger = logging.getLogger(__name__)

            # Create console handler
            handler = logging.StreamHandler(sys.stdout)

            # Create formatter
            formatter = logging.Formatter('%(asctime)s -- %(name)s -- %(levelname)s - %(message)s')

            # Add formatter to ch
            handler.setFormatter(formatter)

            # Add handler to logger and set level
            GOCAD_VESSEL.logger.addHandler(handler)

        GOCAD_VESSEL.logger.setLevel(debug_level)

        self.logger = GOCAD_VESSEL.logger 

        self.STOP_ON_EXC = stop_on_exc

        # Initialise input vars
        self.base_xyz = base_xyz
        self.group_name = group_name
        self.nondefault_coords = nondefault_coords

        self.header_name = ""
        ''' Contents of the name field in the header
        '''

        self.prop_dict = {}
        ''' Dictionary of PROPS objects, stores GOCAD "PROPERTY" objects
            Dictionary index is the PROPERTY number e.g. '1', '2', '3' ...
        '''

        self.invert_zaxis = False
        ''' Set to true if z-axis inversion is turned on in this GOCAD file
        '''

        self.local_props = OrderedDict()
        ''' OrderedDict of PROPS objects for attached PVRTX and PATOM properties
 
        '''

        self.is_ts = False
        ''' True iff it is a GOCAD TSURF file
        '''

        self.is_vs = False
        ''' True iff it is a GOCAD VSET file
        '''

        self.is_pl = False
        ''' True iff it is a GOCAD PLINE file
        '''

        self.is_vo = False
        ''' True iff it is a GOCAD VOXET file
        '''

        self.xyz_mult = [1.0, 1.0, 1.0]
        ''' Used to convert to metres if the units are in kilometres
        '''

        self.xyz_unit = [None, None, None]
        ''' Units of XYZ axes
        ''' 

        self.axis_origin = None
        ''' Origin of XYZ axes
        '''

        self.axis_u = None
        ''' Length of u-axis
        '''

        self.axis_v = None
        ''' Length of v-axis
        '''

        self.axis_w = None
        ''' Length of w-axis
        '''

        self.vol_dims = None
        ''' 3 dimensional size of voxel volume
        '''

        self.axis_min = None
        ''' 3 dimensional minimum point of voxel volume
        '''

        self.axis_max = None
        ''' 3 dimensional maximum point of voxel volume
        '''

        self.flags_array_length = 0
        ''' Size of flags file
        '''

        self.flags_bit_length = 0
        ''' Number of bit in use in flags file
        '''

        self.flags_bit_size = 0
        ''' Size (number of bytes) of each element in flags file
        '''

        self.flags_offset = 0
        ''' Offset within the flags file  where data starts
        '''

        self.flags_file = ""
        ''' Name of flags file associated with voxel file
        '''

        self.region_dict = {}
        ''' Labels and bit numbers for each region in a flags file, key is number (as string)
        '''

        self.flags_dict = {}
        '''  val is region name, key is (x,y,z) tuple
        '''

        self.np_filename = ""
        ''' Filename of GOCAD file without path or extension
        '''

        self.coord_sys_name = "DEFAULT"
        ''' Name of the GOCAD coordinate system
        '''

        self.usesDefaultCoords = True
        ''' Uses default coordinates
        '''


    def __handle_exc(self, exc):
        ''' If STOP_ON_EXC is set or debug is on, print details of exception and stop
            exc - exception
        ''' 
        if self.logger.getEffectiveLevel() == logging.DEBUG or self.STOP_ON_EXC:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            if self.STOP_ON_EXC:
                print("DEBUG MODE: CAUGHT EXCEPTION:")
                print(exc)
                print(traceback.format_exception(exc_type, exc_value, exc_traceback))
                sys.exit(1)
            self.logger.debug("DEBUG MODE: CAUGHT EXCEPTION:")
            self.logger.debug(exc)
            self.logger.debug(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            sys.exit(1)

    def __repr__(self):
        ''' A very basic print friendly representation
        '''
        return "is_ts {0} is_vs {1} is_pl {2} is_vo {3} len(vrtx_arr)={4}\n".format(self.is_ts, self.is_vs, self.is_pl, self.is_vo, len(self._vrtx_arr))


    def is_single_layer_vo(self):
        ''' Returns True if this is extracted from a GOCAD VOXEL that only has a single layer and should be converted into a PNG
            instead of a GLTF
        '''
        return self.is_vo and self.vol_dims[2]==1


    def make_vertex_dict(self):
        ''' Make a dictionary to associate vertex insertion order with vertex sequence number
            Ordinarily the vertex sequence number is the same as the insertion order in the vertex
            array, but some GOCAD files have missing vertices etc.
            The first element starts at '1'
        '''
        vert_dict = {}
        idx = 1
        # Assign vertices to dict
        for v in self._vrtx_arr:
            vert_dict[v.n] = idx
            idx += 1

        # Assign atoms to dict
        for atom in self._atom_arr:
            idx = 1
            for vert in self._vrtx_arr:
                if vert.n == atom.v:
                    vert_dict[atom.n] = idx
                    break
                idx += 1
        return vert_dict


    def process_gocad(self, src_dir, filename_str, file_lines):
        ''' Extracts details from gocad file. This should be called before other functions!
            filename_str - filename of gocad file
            file_lines - array of strings of lines from gocad file
            Returns true if could process file
        '''
        self.logger.debug("process_gocad(%s,%s,%d)", src_dir, filename_str, len(file_lines))

        # State variable for reading first line
        firstLine = True
        
        # For being within header
        inHeader = False
        
        # For being within coordinate header
        inCoord = False
        
        # Within attached binary file property class header (PROP_FILE)
        inPropClassHeader = False
        
        # Within header for properties attached to points (PVRTX, PATOM)
        inLocalPropClassHeader = False

        # Index for property class header currently being parsed
        propClassIndex = ''
        
        # For keeping track of the ID of VRTX, ATOM, PVRTX, SEG etc.
        seq_no = 0
        seq_no_prev = -1

        fileName, fileExt = os.path.splitext(filename_str)
        self.np_filename = os.path.basename(fileName)
        for line in file_lines:
            line_str = line.rstrip(' \n\r').upper()
            # Look out for double-quoted strings
            while line_str.count('"') >= 2:
                before_tup = line_str.partition('"')
                after_tup = before_tup[2].partition('"')
                line_str = before_tup[0]+" "+after_tup[0].strip(' ').replace(' ','_')+" "+after_tup[2]
            splitstr_arr_raw = line.rstrip(' \n\r').split()
            splitstr_arr = line_str.split()

            # Skip blank lines
            if len(splitstr_arr)==0:
                continue

            self.logger.debug("splitstr_arr = %s", repr(splitstr_arr))

            # Check that we have a GOCAD file that we can process
            # Nota bene: This will return if called for the header of a GOCAD group file
            if firstLine:
                firstLine = False
                if not self.__setType(fileExt, line_str):
                    self.logger.debug("process_gocad() Can't set type, return False")
                    return False
                continue

            # Skip the subsets keywords
            if splitstr_arr[0] in ["SUBVSET", "ILINE", "TFACE", "TVOLUME"]:
                self.logger.debug("Skip subset keywords")
                continue

            # Skip control nodes (used to denote fixed points in GOCAD)
            if splitstr_arr[0] == "CNP":
                self.logger.debug("Skip control nodes")
                continue

            # Are we within coordinate system header?
            elif splitstr_arr[0] == "GOCAD_ORIGINAL_COORDINATE_SYSTEM":
                inCoord = True
                self.logger.debug("inCoord True")
            
            # Are we leaving coordinate system header?
            elif splitstr_arr[0] == "END_ORIGINAL_COORDINATE_SYSTEM":
                inCoord = False
                self.logger.debug("inCoord False")
            
            # Within coordinate system header and not using the default coordinate system
            elif inCoord and splitstr_arr[0] == "NAME":
                self.coord_sys_name = splitstr_arr[1]
                if splitstr_arr[1] != "DEFAULT":
                    self.usesDefaultCoords = False
                    self.logger.debug("usesDefaultCoords False")

                    # FIXME: I can't support non default coords yet - need to enter via command line?
                    # If does not support default coords then exit
                    if not self.nondefault_coords:
                        self.logger.warning("SORRY - Does not support non-DEFAULT coordinates: %s", repr(splitstr_arr[1]))
                        self.logger.debug("process_gocad() return False")
                        return False 
                
            # Does coordinate system use inverted z-axis?
            elif inCoord and splitstr_arr[0] == "ZPOSITIVE" and splitstr_arr[1] == "DEPTH":
                self.invert_zaxis=True
                self.logger.debug("invert_zaxis = %s", repr(self.invert_zaxis))
            
            # Are we in the header?
            elif splitstr_arr[0] == "HEADER":
                inHeader = True
                self.logger.debug("inHeader = %s", repr(inHeader))

            # Are we in the property class header?
            elif splitstr_arr[0] == "PROPERTY_CLASS_HEADER":
                propClassIndex = splitstr_arr[1]
                # There are two kinds of PROPERTY_CLASS_HEADER
                # First, properties attached to points
                if splitstr_arr[2] == '{':
                    inLocalPropClassHeader = True
                # Properties of binary files 
                elif splitstr_arr[3] == '{':
                    if propClassIndex not in self.prop_dict:
                        self.prop_dict[propClassIndex] = PROPS(splitstr_arr[2])
                    inPropClassHeader = True
                else:
                    self.logger.error("ERROR - Cannot parse property header")
                    sys.exit(1)
                self.logger.debug("inPropClassHeader = %s", repr(inPropClassHeader))

            # Are we out of the header?    
            elif inHeader and splitstr_arr[0] == "}":
                inHeader = False
                self.logger.debug("inHeader = %s", repr(inHeader))

            # Property class headers for binary files
            elif inPropClassHeader:
                # Leaving header
                if splitstr_arr[0] == "}":
                    inPropClassHeader = False
                    propClassIndex = ''
                    self.logger.debug("inPropClassHeader = %s", repr(inPropClassHeader))
                else:
                    # When in the PROPERTY CLASS headers, get the colour table
                    self.__parse_property_header(self.prop_dict[propClassIndex], line_str)

            # Property class headers for local points
            elif inLocalPropClassHeader:
                # Leaving header
                if splitstr_arr[0] == "}":
                    inLocalPropClassHeader = False
                    propClassIndex = ''
                    self.logger.debug("inLocalPropClassHeader = %s", repr(inLocalPropClassHeader))
                else:
                    # When in the PROPERTY CLASS headers, get the colour table
                    if propClassIndex in self.local_props:
                        self.__parse_property_header(self.local_props[propClassIndex], line_str)

            # When in the HEADER get the colours
            elif inHeader:
                name_str, sep, value_str = line_str.partition(':')
                name_str = name_str.strip()
                value_str = value_str.strip()
                self.logger.debug("inHeader name_str = %s value_str = %s", name_str, value_str)
                if name_str=='*SOLID*COLOR' or name_str=='*ATOMS*COLOR':
                    # Colour can either be spaced RGBA/RGB floats, or '#' + 6 digit hex string
                    try:
                        if value_str[0]!='#':
                            rgbsplit_arr = value_str.split(' ')
                            if len(rgbsplit_arr)==3:
                                self.rgba_tup = (float(rgbsplit_arr[0]), float(rgbsplit_arr[1]), float(rgbsplit_arr[2]), 1.0)
                            elif len(rgbsplit_arr)==4:
                                self.rgba_tup = (float(rgbsplit_arr[0]), float(rgbsplit_arr[1]), float(rgbsplit_arr[2]), float(rgbsplit_arr[3]))
                            else:
                                self.logger.debug("Could not parse colour %s", repr(value_str))
                        else:
                            self.rgba_tup = (float(int(value_str[1:3],16))/255.0, float(int(value_str[3:5],16))/255.0, float(int(value_str[5:7],16))/255.0, 1.0) 
                    except (ValueError, OverflowError, IndexError) as exc:
                        self.__handle_exc(exc)
                        self.rgba_tup = (1.0, 1.0, 1.0, 1.0)

                    self.logger.debug("self.rgba_tup = %s", repr(self.rgba_tup))
           
                if name_str=='NAME':
                    self.header_name = value_str.replace('/','-')
                    self.logger.debug("self.header_name = %s", self.header_name)

            # Axis units - check if units are kilometres, and update coordinate multiplier
            elif splitstr_arr[0] == "AXIS_UNIT":
                for idx in range(0,3):
                    unit_str = splitstr_arr[idx+1].strip('"').strip(' ').strip("'")
                    if unit_str=='KM':
                        self.xyz_mult[idx] =  1000.0
                    # Warn if not metres or kilometres or unitless etc.
                    elif unit_str not in ['M', 'UNITLESS', 'NUMBER', 'MS']:
                        self.logger.warning("WARNING - nonstandard units in 'AXIS_UNIT' "+ splitstr_arr[idx+1])
                    else:
                        self.xyz_unit[idx] = unit_str

            # Property names, this is not the class names
            elif splitstr_arr[0] == "PROPERTIES":
                if len(self.local_props) == 0:
                    for class_name in splitstr_arr[1:]:
                        self.local_props[class_name] = PROPS(class_name)
                self.logger.debug(" properties list = %s", repr(splitstr_arr[1:]))

            # These are the property names for the point properties (e.g. PVRTX, PATOM)
            elif splitstr_arr[0] == "PROPERTY_CLASSES":
                if len(self.local_props) == 0:
                    for class_name in splitstr_arr[1:]:
                        self.local_props[class_name] = PROPS(class_name)
                self.logger.debug(" property classes = %s", repr(splitstr_arr[1:]))

            # This is the number of floats/ints for each property, usually it is '1',
            # but XYZ values are '3'
            elif splitstr_arr[0] == "ESIZES":
                idx = 1
                for prop_obj in self.local_props.values():
                    try:
                        prop_obj.data_sz = int(splitstr_arr[idx])
                    except (ValueError, IndexError, OverflowError) as exc:
                        self.__handle_exc(exc)
                    idx += 1 
                self.logger.debug(" property_sizes = %s", repr(splitstr_arr[1:]))

            # Read values representing no data for this property at a coordinate point
            elif splitstr_arr[0] == "NO_DATA_VALUES":
                idx = 1
                for prop_obj in self.local_props.values():
                    try:
                        converted, fp  = self.__parse_float(splitstr_arr[idx])
                        if converted:
                            prop_obj.no_data_marker = fp
                            self.logger.debug("prop_obj.no_data_marker = %f", prop_obj.no_data_marker)
                    except IndexError as exc:
                        self.__handle_exc(exc)
                    idx += 1
                self.logger.debug(" property_nulls = %s", repr(splitstr_arr[1:]))
                
            # Atoms, with or without properties
            elif splitstr_arr[0] == "ATOM" or splitstr_arr[0] == 'PATOM':
                seq_no_prev = seq_no
                try:
                    seq_no = int(splitstr_arr[1])
                    v_num = int(splitstr_arr[2])
                except (OverflowError, ValueError, IndexError) as exc:
                    self.__handle_exc(exc)
                    seq_no = seq_no_prev
                else:
                    if self._check_vertex(v_num):
                        self._atom_arr.append(self.ATOM(seq_no, v_num))
                    else:
                        self.logger.error("ERROR - ATOM refers to VERTEX that has not been defined yet")
                        self.logger.error("    seq_no = %d", seq_no)
                        self.logger.error("    v_num = %d", v_num)
                        self.logger.error("    line = %s", line_str)
                        sys.exit(1)

                    # Atoms with attached properties
                    if splitstr_arr[0] == "PATOM":
                        try:
                            vert_dict = self.make_vertex_dict()
                            self.__parse_props(splitstr_arr, self._vrtx_arr[vert_dict[v_num]].xyz, True)
                        except IndexError as exc:
                            self.__handle_exc(exc)
                  
            # Grab the vertices and properties, does not care if there are gaps in the sequence number
            elif splitstr_arr[0] == "PVRTX" or  splitstr_arr[0] == "VRTX":
                seq_no_prev = seq_no
                try:
                    seq_no = int(splitstr_arr[1])
                    is_ok, x_flt, y_flt, z_flt = self.__parse_XYZ(True, splitstr_arr[2], splitstr_arr[3], splitstr_arr[4], True)
                    self.logger.debug("ParseXYZ %s %f %f %f from %s %s %s", repr(is_ok), x_flt, y_flt, z_flt,  splitstr_arr[2], splitstr_arr[3], splitstr_arr[4])
                except (IndexError, ValueError, OverflowError) as exc:
                    self.__handle_exc(exc)
                    seq_no = seq_no_prev
                else:
                    if is_ok:
                        # Add vertex
                        if self.invert_zaxis:
                            z_flt = -z_flt
                        self._vrtx_arr.append(self.VRTX(seq_no, (x_flt, y_flt, z_flt)))

                        # Vertices with attached properties
                        if splitstr_arr[0] == "PVRTX":
                            self.__parse_props(splitstr_arr, (x_flt, y_flt, z_flt))

            # Grab the triangular edges
            elif splitstr_arr[0] == "TRGL":
                seq_no_prev = seq_no
                try:
                    seq_no = int(splitstr_arr[1])
                    is_ok, a_int, b_int, c_int = self.__parse_XYZ(False, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3], False, False)
                except (IndexError, ValueError, OverflowError) as exc:
                    self.__handle_exc(exc)
                    seq_no = seq_no_prev
                else:
                    if is_ok:
                        self._trgl_arr.append(self.TRGL(seq_no, (a_int, b_int, c_int)))

            # Grab the segments
            elif splitstr_arr[0] == "SEG":
                try:
                    a_int = int(splitstr_arr[1])
                    b_int = int(splitstr_arr[2])
                except (IndexError, ValueError) as exc:
                    self.__handle_exc(exc)
                    seq_no = seq_no_prev
                else:
                    self._seg_arr.append(self.SEG(seq_no, (a_int, b_int)))

            # Extract binary file name
            elif splitstr_arr[0] == "PROP_FILE":
                self.prop_dict[splitstr_arr[1]].file_name = os.path.join(src_dir, splitstr_arr_raw[2])
                self.logger.debug("self.prop_dict[%s].file_name = %s", splitstr_arr[1], self.prop_dict[splitstr_arr[1]].file_name)

            # Size of each float in binary file (measured in bytes)
            elif splitstr_arr[0] == "PROP_ESIZE":
                try:
                    self.prop_dict[splitstr_arr[1]].data_sz = int(splitstr_arr[2])
                    self.logger.debug("self.prop_dict[%s].data_sz = %d", splitstr_arr[1], self.prop_dict[splitstr_arr[1]].data_sz)
                except (IndexError, ValueError) as exc:
                    self.__handle_exc(exc)

            # Is property an integer ? What size?
            elif splitstr_arr[0] == "PROP_STORAGE_TYPE":
                if splitstr_arr[2] == "OCTET":
                    self.prop_dict[splitstr_arr[1]].data_type = "b"
                elif splitstr_arr[2] == "SHORT":
                    self.prop_dict[splitstr_arr[1]].data_type = "h"
                else:
                    self.logger.error("ERROR - unknown storage type")
                    sys.exit(1)
                self.logger.debug("self.prop_dict[%s].data_type = %s", splitstr_arr[1], self.prop_dict[splitstr_arr[1]].data_type)

            # Is property a signed integer ?
            elif splitstr_arr[0] == "PROP_SIGNED":
                self.prop_dict[splitstr_arr[1]].signed_int = (splitstr_arr[2] == "1")
                self.logger.debug("self.prop_dict[%s].signed_int = %s", splitstr_arr[1], repr(self.prop_dict[splitstr_arr[1]].signed_int))

            # Cannot process IBM-style floats
            elif splitstr_arr[0] == "PROP_ETYPE":
                if splitstr_arr[2] != "IEEE":
                    self.logger.error("ERROR - Cannot process %s type floating points", splitstr_arr[1])
                    sys.exit(1)

            # Cannot process SEGY formats 
            elif splitstr_arr[0] == "PROP_EFORMAT":
                if splitstr_arr[2] != "RAW":
                    self.logger.error("ERROR - Cannot process %s format floating points", splitstr_arr[1])
                    sys.exit(1)

            # FIXME: Cannot do offsets within binary file
            elif splitstr_arr[0] == "PROP_OFFSET":
                if int(splitstr_arr[2]) != 0:
                    self.logger.error("ERROR - Cannot process offsets of more than 0")
                    sys.exit(1)

            # The number that is used to represent 'no data'
            elif splitstr_arr[0] == "PROP_NO_DATA_VALUE":
                converted, fp = self.__parse_float(splitstr_arr[2])
                if converted:
                    self.prop_dict[splitstr_arr[1]].no_data_marker = fp
                    self.logger.debug("self.prop_dict[%s].no_data_marker = %f", splitstr_arr[1], self.prop_dict[splitstr_arr[1]].no_data_marker)

            # Layout of VOXET data
            elif splitstr_arr[0] == "AXIS_O":
                is_ok, x_flt, y_flt, z_flt = self.__parse_XYZ(True, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3])
                if is_ok:
                    self.axis_origin = (x_flt, y_flt, z_flt)
                    self.logger.debug("self.axis_origin = %s", repr(self.axis_origin))

            elif splitstr_arr[0] == "AXIS_U":
                is_ok, x_flt, y_flt, z_flt = self.__parse_XYZ(True, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3], False, False)
                if is_ok:
                    self.axis_u = (x_flt, y_flt, z_flt)
                    self.logger.debug("self.axis_u = %s", repr(self.axis_u))

            elif splitstr_arr[0] == "AXIS_V":
                is_ok, x_flt, y_flt, z_flt = self.__parse_XYZ(True, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3], False, False)
                if is_ok:
                    self.axis_v = (x_flt, y_flt, z_flt)
                    self.logger.debug("self.axis_v = %s", repr(self.axis_v))

            elif splitstr_arr[0] == "AXIS_W":
                is_ok, x_flt, y_flt, z_flt = self.__parse_XYZ(True, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3], False, False)
                if is_ok:
                    self.axis_w = (x_flt, y_flt, z_flt)
                    self.logger.debug("self.axis_w= %s", repr(self.axis_w))

            elif splitstr_arr[0] == "AXIS_N":
                is_ok, x_int, y_int, z_int = self.__parse_XYZ(False, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3], False, False)
                if is_ok:
                    self.vol_dims = (x_int, y_int, z_int)
                    self.logger.debug("self.vol_dims= %s", repr(self.vol_dims))

            elif splitstr_arr[0] == "AXIS_MIN":
                is_ok, x_int, y_int, z_int = self.__parse_XYZ(True, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3], False, False)
                if is_ok:
                    self.axis_min = (x_int, y_int, z_int)
                    self.logger.debug("self.axis_min= %s", repr(self.axis_min))

            elif splitstr_arr[0] == "AXIS_MAX":
                is_ok, x_int, y_int, z_int = self.__parse_XYZ(True, splitstr_arr[1], splitstr_arr[2], splitstr_arr[3], False, False)
                if is_ok:
                    self.axis_max = (x_int, y_int, z_int)
                    self.logger.debug("self.axis_max= %s", repr(self.axis_max))

            elif splitstr_arr[0] == "FLAGS_ARRAY_LENGTH":
                is_ok, l = self.__parse_int(splitstr_arr[1])
                if is_ok:
                    self.flags_array_length = l
                    self.logger.debug("self.flags_array_length= %d", self.flags_array_length)

            elif splitstr_arr[0] == "FLAGS_BIT_LENGTH":
                is_ok, l = self.__parse_int(splitstr_arr[1])
                if is_ok:
                    self.flags_bit_length = l
                    self.logger.debug("self.flags_bit_length= %d", self.flags_bit_length)

            elif splitstr_arr[0] == "FLAGS_ESIZE":
                is_ok, l = self.__parse_int(splitstr_arr[1])
                if is_ok:
                    self.flags_bit_size = l
                    self.logger.debug("self.flags_bit_size= %d", self.flags_bit_size)

            elif splitstr_arr[0] == "FLAGS_OFFSET":
                is_ok, l = self.__parse_int(splitstr_arr[1])
                if is_ok:
                    self.flags_offset = l
                    self.logger.debug("self.flags_offset= %d", self.flags_offset)

            elif splitstr_arr[0] == "FLAGS_FILE":
                self.flags_file =  os.path.join(src_dir, splitstr_arr_raw[1])
                self.logger.debug("self.flags_file= %s", self.flags_file)

            elif splitstr_arr[0] == "REGION":
                self.region_dict[splitstr_arr[2]] = splitstr_arr[1]
                self.logger.debug("self.region_dict[%s] = %s", splitstr_arr[2], splitstr_arr[1])
                
            # END OF TEXT PROCESSING LOOP

        self.logger.debug("process_gocad() filename_str = %s", filename_str)
            
        # Calculate max and min of properties
        for prop_obj in self.local_props.values():
            prop_obj.data_stats = { 'min': sys.float_info.max, 'max': -sys.float_info.max }
            # Some properties are XYZ, so only take X for calculating max and min
            if len(prop_obj.data.values()) > 0:
                first_val_list = list(map(lambda x: x if type(x) is float else x[0], prop_obj.data.values()))
                prop_obj.data_stats['max'] = max(list(first_val_list))
                prop_obj.data_stats['min'] = min(list(first_val_list))

        self.logger.debug("process_gocad() returns")
        # Read in any binary data files and flags files attached to voxel files
        retVal = self.__read_voxel_files()
        return retVal


    def __setType(self, fileExt, firstLineStr):
        ''' Sets the type of GOCAD file: TSURF, VOXEL, PLINE etc.
            fileExt - the file extension
            firstLineStr - first line in the file
            Returns True if it could determine the type of file
            Will return False when given the header of a GOCAD group file, since
            cannot create a vessel object from the group file itself, only from the group members
        '''
        self.logger.debug("setType(%s,%s)", fileExt, firstLineStr)
        ext_str = fileExt.lstrip('.').upper()
        # Look for other GOCAD file types within a group file
        if ext_str=='GP':
            found = False
            for key in self.GOCAD_HEADERS:
                if key!='GP' and firstLineStr in self.GOCAD_HEADERS[key]:
                    ext_str = key
                    found = True
                    break
            if not found:
                return False

        if ext_str in self.GOCAD_HEADERS:
            if ext_str=='TS' and firstLineStr in self.GOCAD_HEADERS['TS']:
                self.is_ts = True
                return True
            elif ext_str=='VS' and firstLineStr in self.GOCAD_HEADERS['VS']:
                self.is_vs = True
                return True
            elif ext_str=='PL' and firstLineStr in self.GOCAD_HEADERS['PL']:
                self.is_pl = True
                return True
            elif ext_str=='VO' and firstLineStr in self.GOCAD_HEADERS['VO']:
                self.is_vo = True
                return True

        return False


    def __parse_property_header(self, prop_obj, line_str):
        ''' Parses the PROPERTY header, extracting the colour table info and storing it in PROPS object
            prop_obj - a PROPS object to store the data
            line_str - current line
        '''
        name_str, sep, value_str = line_str.partition(':')
        name_str = name_str.strip()
        value_str = value_str.strip()
        if name_str=='*COLORMAP*SIZE':
            self.logger.debug("colourmap-size %s", value_str)
        elif name_str=='*COLORMAP*NBCOLORS':
            self.logger.debug("numcolours %s", value_str)
        elif name_str=='HIGH_CLIP':
            self.logger.debug("highclip %s", value_str)
        elif name_str=='LOW_CLIP':
            self.logger.debug("lowclip %s", value_str)
        # Read in the name of the colour map for this property
        elif name_str=='COLORMAP':
            prop_obj.colourmap_name = value_str
            self.logger.debug("prop_obj.colourmap_name = %s", prop_obj.colourmap_name)
        # Read in the colour map for this property
        elif name_str=='*COLORMAP*'+prop_obj.colourmap_name+'*COLORS':
            lut_arr = value_str.split(' ')
            for idx in range(0, len(lut_arr), 4):
                try:
                    prop_obj.colour_map[int(lut_arr[idx])] = (float(lut_arr[idx+1]), float(lut_arr[idx+2]), float(lut_arr[idx+3]))
                    self.logger.debug("prop_obj.colour_map = %s", prop_obj.colour_map)
                except (IndexError, OverflowError, ValueError) as exc:
                    self.__handle_exc(exc)



    def __read_voxel_files(self):
        ''' Open up and read binary voxel file
        '''
        if self.is_vo and len(self.prop_dict)>0:
            for file_idx, prop_obj in self.prop_dict.items():
                # Sometimes filename needs a .vo on the end
                if not os.path.isfile(prop_obj.file_name) and prop_obj.file_name[-2:]=="@@" and \
                                              os.path.isfile(prop_obj.file_name+".vo"):
                    prop_obj.file_name += ".vo"

                try:
                    # Check file size first
                    file_sz = os.path.getsize(prop_obj.file_name)
                    num_voxels = prop_obj.data_sz*self.vol_dims[0]*self.vol_dims[1]*self.vol_dims[2]
                    if file_sz != num_voxels:
                        self.logger.error("SORRY - Cannot process voxel file - length (%d) is not correct %s", num_voxels, prop_obj.file_name)
                        sys.exit(1)

                    # Initialise data array to zeros
                    prop_obj.data = numpy.zeros((self.vol_dims[0], self.vol_dims[1], self.vol_dims[2]))

                    # Prepare 'numpy' dtype object for binary float, integer signed/unsigned data types
                    dt = prop_obj.make_numpy_dtype()

                    # Read entire file, assumes file small enough to store in memory
                    self.logger.info("Reading binary file: %s", prop_obj.file_name)
                    f_arr = numpy.fromfile(prop_obj.file_name, dtype=dt)
                    fl_idx = 0
                    prop_obj.data_stats = { 'max': -sys.float_info.max, 'min': sys.float_info.max }
                    for z in range(self.vol_dims[2]):
                        for y in range(self.vol_dims[1]):
                            for x in range(self.vol_dims[0]):
                                converted, fp = self.__parse_float(f_arr[fl_idx], prop_obj.no_data_marker)
                                fl_idx +=1
                                if not converted:
                                    continue
                                prop_obj.data[x][y][z] = fp
                                if (prop_obj.data[x][y][z] > prop_obj.data_stats['max']):
                                    prop_obj.data_stats['max'] = prop_obj.data[x][y][z]
                                if (prop_obj.data[x][y][z] < prop_obj.data_stats['min']):
                                    prop_obj.data_stats['min'] = prop_obj.data[x][y][z]
                                self._calc_minmax( self.axis_origin[0]+float(x)/self.vol_dims[0]*self.axis_u[0],
                                                   self.axis_origin[1]+float(y)/self.vol_dims[1]*self.axis_v[1],
                                                   self.axis_origin[2]+float(z)/self.vol_dims[2]*self.axis_w[2] )
                                        
                except IOError as e:
                    self.logger.error("SORRY - Cannot process voxel file IOError %s %s %s", prop_obj.file_name, str(e), e.args)
                    sys.exit(1)
                    

            # Open up flags file and look for regions
            if self.flags_file!='':
                if self.flags_array_length != self.vol_dims[0]*self.vol_dims[1]*self.vol_dims[2]:
                    self.logger.warning("SORRY - Cannot process voxel file, inconsistent size between data file and flag file")
                    self.logger.debug("process_gocad() return False")
                    return False
                # Check file does not exist, sometimes needs a '.vo' on the end
                if not os.path.isfile(self.flags_file) and self.flags_file[-2:]=="@@" and \
                                                                os.path.isfile(self.flags_file+".vo"):
                    self.flags_file += ".vo"

                try: 
                    # Check file size first
                    file_sz = os.path.getsize(self.flags_file)
                    num_voxels = self.flags_bit_size*self.vol_dims[0]*self.vol_dims[1]*self.vol_dims[2]
                    if file_sz != num_voxels:
                        self.logger.error("SORRY - Cannot process voxel flags file - length (%d) is not correct %s", num_voxels, self.flags_file)
                        sys.exit(1)

                    # Initialise data array to zeros
                    flag_data = numpy.zeros((self.vol_dims[0], self.vol_dims[1], self.vol_dims[2]))

                    # Prepare 'numpy' dtype object for binary float, integer signed/unsigned data types
                    dt =  numpy.dtype(('B',(self.flags_bit_size)))

                    # Read entire file, assumes file small enough to store in memory
                    self.logger.info("Reading binary flags file: %s", self.flags_file)
                    f_arr = numpy.fromfile(self.flags_file, dtype=dt)
                    f_idx = self.flags_offset
                    # self.debug('self.region_dict.keys() = %s', self.region_dict.keys())
                    for z in range(0,self.vol_dims[2]):
                        for y in range(0, self.vol_dims[1]):
                            for x in range(0, self.vol_dims[0]):
                                # self.logger.debug("%d %d %d %d => %s", x, y, z, f_idx, repr(f_arr[f_idx]))
                                bit_mask = ''
                                # Single bytes are not returned as arrays
                                if self.flags_bit_size==1:
                                    bit_mask = '{0:08b}'.format(f_arr[f_idx])
                                else:
                                    for b in range(self.flags_bit_size-1, -1, -1):
                                        bit_mask += '{0:08b}'.format(f_arr[f_idx][b])
                                # self.logger.debug('bit_mask= %s', bit_mask)
                                cnt = self.flags_bit_size*8-1
                                for bit in bit_mask:
                                    if str(cnt) in self.region_dict and bit=='1':
                                        key = self.region_dict[str(cnt)]
                                        # self.logger.debug('cnt = %d bit = %d', cnt, bit)
                                        # self.logger.debug('key = %s', key)
                                        self.flags_dict[(x,y,z)] = key
                                    cnt -= 1
        
                                f_idx += 1
                    
                except IOError as e:
                    self.logger.error("SORRY - Cannot process voxel flags file, IOError %s %s %s", self.flags_file, str(e), e.args)
                    self.logger.debug("process_gocad() return False")
                    return False
        self.logger.debug('self.flags_dict= %s', repr(self.flags_dict))
        return True



    def __parse_props(self, splitstr_arr, coord_tup, is_patom = False):
        ''' This parses a line of properties associated with a PVTRX or PATOM line
            splitstr_arr - array of strings representing line with properties
            coord_tup - (X,Y,Z) float tuple of the coordinates
            is_patom - this is from a PATOM, default False
        '''
        if is_patom:
            # For PATOM, properties start at the 4th column
            col_idx = 3
        else:
            # For PVRTX, properties start at the 6th column
            col_idx = 5

        # Loop over each property in line
        for prop_obj in self.local_props.values():
            # Property has one float
            if prop_obj.data_sz == 1:
                fp_str = splitstr_arr[col_idx]
                # Skip GOCAD control nodes e.g. 'CNXY', 'CNXYZ'
                if fp_str[:2].upper()=='CN':
                    col_idx += 1
                    fp_str = splitstr_arr[col_idx]
                converted, fp = self.__parse_float(fp_str, prop_obj.no_data_marker)
                if converted:
                    prop_obj.data[coord_tup] = fp
                    self.logger.debug("prop_obj.data[%s] = %f", repr(coord_tup), fp)
                col_idx += 1
            # Property has 3 floats i.e. XYZ
            elif prop_obj.data_sz == 3:
                fp_strX = splitstr_arr[col_idx]
                # Skip GOCAD control nodes e.g. 'CNXY', 'CNXYZ'
                if fp_strX[:2].upper()=='CN':
                    col_idx += 1
                    fp_strX = splitstr_arr[col_idx]
                fp_strY = splitstr_arr[col_idx+1]
                fp_strZ = splitstr_arr[col_idx+2]
                convertedX, fpX = self.__parse_float(fp_strX, prop_obj.no_data_marker)
                convertedY, fpY = self.__parse_float(fp_strY, prop_obj.no_data_marker)
                convertedZ, fpZ = self.__parse_float(fp_strZ, prop_obj.no_data_marker)
                if convertedZ and convertedY and convertedX:
                    prop_obj.data[coord_tup] = (fpX, fpY, fpZ)
                    self.logger.debug("prop_obj.data[%s] = (%f,%f,%f)", repr(coord_tup), fpX, fpY, fpZ)
                col_idx += 3
            else:
                self.logger.error("ERROR - Cannot process property size of != 3 and !=1: %d %s", prop_obj.data_sz, repr(prop_obj))
                sys.exit(1)


    def __parse_float(self, fp_str, null_val=None):
        ''' Converts a string to float, handles infinite values 
            fp_str - string to convert to a float
            null_val - value representing 'no data'
            Returns a boolean and a float
            If could not convert then return (False, None) else if 'null_val' is defined return (False, null_val)
        '''
        # Handle GOCAD's C++ floating point infinity for Windows and Linux
        self.logger.debug("fp_str = %s", fp_str)
        if fp_str in ["1.#INF","INF"]:
            fp = sys.float_info.max
        elif fp_str in ["-1.#INF","-INF"]:
            fp = -sys.float_info.max
        else:
            try:
                fp = float(fp_str)
                if null_val != None and fp == null_val:
                    return False, null_val
            except (OverflowError, ValueError) as exc:
                self.__handle_exc(exc)
                return False, 0.0
        return True, fp

           
    def __parse_int(self, int_str, null_val=None):
        ''' Converts a string to an int
            int_str - string to convert to int
            null_val - value representing 'no data'
            Returns a boolean and an integer
            If could not convert then return (False, None) else if 'null_val' is defined return (False, null_val)
        '''
        try:
            num = int(int_str)
        except (OverflowError, ValueError) as exc:
             self.__handle_exc(exc)
             return False, null_val
        return True, num 


    def __parse_XYZ(self, is_float, x_str, y_str, z_str, do_minmax=False, convert = True):
        ''' Helpful function to read XYZ cooordinates
            is_float - if true parse x y z as floats else try integers
            x_str, y_str, z_str - X,Y,Z coordinates in string form
            do_minmax - record the X,Y,Z coords for calculating extent
            convert - convert from kms to metres if necessary
            Returns four parameters: success - true if could convert the strings to floats
                                     x,y,z - floating point values, converted to metres if units are kms
        '''
        x = y = z = None
        if is_float:
            converted1, x = self.__parse_float(x_str)
            converted2, y = self.__parse_float(y_str)
            converted3, z = self.__parse_float(z_str)
            if not converted1 or not converted2 or not converted3:
                return False, None, None, None
        else:
            try:
                x = int(x_str)
                y = int(y_str)
                z = int(z_str)
            except (OverflowError, ValueError) as exc:
                self.__handle_exc(exc)
                return False, None, None, None

        # Convert to metres if units are kms
        if convert and isinstance(x, float):
            x *= self.xyz_mult[0]
            y *= self.xyz_mult[1]
            z *= self.xyz_mult[2]

        # Calculate minimum and maximum XYZ
        if do_minmax:
            self._calc_minmax(x,y,z)

        return True, x, y, z 



#  END OF GOCAD_VESSEL CLASS
