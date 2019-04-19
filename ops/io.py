import numpy as np
import os
import pandas as pd
import six
import struct
import warnings

import ops.utils
import ops.constants
from ops.external.tifffile_new import imread
# currently needed to save ImageJ-compatible hyperstacks
from ops.external.tifffile_old import imsave

imagej_description = ''.join(['ImageJ=1.49v\nimages=%d\nchannels=%d\nslices=%d',
                              '\nframes=%d\nhyperstack=true\nmode=composite',
                              '\nunit=\\u00B5m\nspacing=8.0\nloop=false\n',
                              'min=764.0\nmax=38220.0\n'])

ramp = list(range(256))
ZERO = [0]*256
RED     = ramp + ZERO + ZERO
GREEN   = ZERO + ramp + ZERO
BLUE    = ZERO + ZERO + ramp
MAGENTA = ramp + ZERO + ramp
GRAY    = ramp + ramp + ramp
CYAN    = ZERO + ramp + ramp

DEFAULT_LUTS = GRAY, GREEN, RED, MAGENTA, CYAN, GRAY, GRAY


def read_lut(lut_string):
    return (pd.read_csv(six.StringIO(lut_string), sep='\s+', header=None)
    	.values.T.flatten())


GLASBEY = read_lut(ops.constants.GLASBEY_INVERTED)


def grid_view(files, bounds, padding=40, with_mask=False):
    """Mask is 1-indexed, zero indicates background.
    """
    padding = int(padding)

    arr = []
    Is = {}
    for filename, bounds_ in zip(files, bounds):
        try:
            I = Is[filename]
        except KeyError:
            I = read_stack(filename, copy=False) 
            Is[filename] = I
        I_cell = ops.utils.subimage(I, bounds_, pad=padding)
        arr.append(I_cell.copy())

    if with_mask:
        arr_m = []
        for i, (i0, j0, i1, j1) in enumerate(bounds):
            shape = i1 - i0 + padding, j1 - j0 + padding
            img = np.zeros(shape, dtype=np.uint16) + i + 1
            arr_m += [img]
        return ops.utils.pile(arr), ops.utils.pile(arr_m)

    return ops.utils.pile(arr)


@ops.utils.memoize(active=False)
def read_stack(filename, copy=True):
    """Read a .tif file into a numpy array, with optional memory mapping.
    """
    data = imread(filename, multifile=False, is_ome=False)
    # preserve inner singleton dimensions
    while data.shape[0] == 1:
        data = np.squeeze(data, axis=(0,))

    if copy:
        data = data.copy()
    return data


def save_stack(name, data, luts=None, display_ranges=None, 
               resolution=1., compress=0, dimensions=None):
    """
    Saves `data`, an array with 5, 4, 3, or 2 dimensions [TxZxCxYxX]. `resolution` 
    can be specified in microns per pixel. Setting `compress` to 1 saves a lot of 
    space for integer masks. The ImageJ lookup table for each channel can be set
    with `luts` (e.g, ops.io.GRAY, ops.io.GREEN, etc). The display range can be set
    with a list of (min, max) pairs for each channel.

    >>> random_data = np.random.randint(0, 2**16, size=(3, 100, 100), dtype=np.uint16)
    >>> luts = ops.io.GREEN, ops.io.RED, ops.io.BLUE
    >>> display_ranges = (0, 60000), (0, 40000), (0, 20000)
    >>> save('random_image', random_data, luts=luts, display_ranges=display_ranges)

    Compatible array data types are:
        bool (converted to uint8 0, 255)
        uint8 
        uint16 
        float32 
        float64 (converted to float32)
    """
    
    if name.split('.')[-1] != 'tif':
        name += '.tif'
    name = os.path.abspath(name)

    if isinstance(data, list):
        data = np.array(data)

    if not (2 <= data.ndim <= 5):
        error = 'Input has shape {}, but number of dimensions must be in range [2, 5]'
        raise ValueError(error.format(data.shape))

    if (data.dtype == np.int64):
        if (data>=0).all() and (data<2**16).all():
            data = data.astype(np.uint16)
        else:
            data = data.astype(np.float32)
            print('Cast int64 to float32')
    if data.dtype == np.float64:
        data = data.astype(np.float32)
        # print('Cast float64 to float32')

    if data.dtype == np.bool:
        data = 255 * data.astype(np.uint8)

    if data.dtype == np.int32:
        if data.min() >= 0 & data.max() < 2**16:
            data = data.astype(np.uint16)
        else:
            raise ValueError('error casting from np.int32 to np.uint16, ' 
                'data out of range')

    if not data.dtype in (np.uint8, np.uint16, np.float32):
        raise ValueError('Cannot save data of type %s' % data.dtype)

    resolution = (1./resolution,)*2

    if not os.path.isdir(os.path.dirname(name)):
        os.makedirs(os.path.dirname(name))

    if data.ndim == 2:
        # simple description
        min, max = single_contrast(data, display_ranges)
        description = imagej_description_2D(min, max)
        imsave(name, data, photometric='minisblack',
           description=description, resolution=resolution, compress=compress)
    else:
        # hyperstack description
        nchannels = data.shape[-3]
        luts, display_ranges = infer_luts_display_ranges(data, luts, 
                                                        display_ranges)

        leading_shape = data.shape[:-2]
        if dimensions is None:
            dimensions = 'TZC'[::-1][:len(leading_shape)][::-1]

        if 'C' not in dimensions:
            # TODO: support lut
            contrast = single_contrast(data, display_ranges)
            description = imagej_description(leading_shape, dimensions, 
                                    contrast=contrast)
            imsave(name, data, photometric='minisblack',
               description=description, resolution=resolution, compress=compress)
        else:
            # the full monty
            description = imagej_description(leading_shape, dimensions)
            # metadata encoding LUTs and display ranges
            # see http://rsb.info.nih.gov/ij/developer/source/ij/io/TiffEncoder.java.html
            tag_50838 = ij_tag_50838(nchannels)
            tag_50839 = ij_tag_50839(luts, display_ranges)

            imsave(name, data, photometric='minisblack', description=description, 
                    resolution=resolution, compress=compress,
                    extratags=[(50838, 'I', len(tag_50838), tag_50838, True),
                               (50839, 'B', len(tag_50839), tag_50839, True),
                               ])


def infer_luts_display_ranges(data, luts, display_ranges):
    """Deal with user input.
    """
    nchannels = data.shape[-3]
    if luts is None:
        luts = DEFAULT_LUTS + (GRAY,) * (nchannels - len(DEFAULT_LUTS))

    if display_ranges is None:
        display_ranges = [None] * data.shape[-3]

    for i, dr in enumerate(display_ranges):
        if dr is None:
            x = data[..., i, :, :]
            display_ranges[i] = x.min(), x.max()
    try:
        luts = luts[:nchannels]
        display_ranges = display_ranges[:nchannels]
    except IndexError:
        error = 'Must provide at least {} luts and display ranges'
        raise IndexError(error.format(nchannels))

    return luts, display_ranges


def single_contrast(data, display_ranges):
    try:
        min, max = np.array(display_ranges).flat[:2]
    except ValueError:
        min, max = data.min(), data.max()
    return min, max


def imagej_description_2D(min, max):
    return 'ImageJ=1.49v\nimages=1\nmin={min}\nmax={max}'.format(min=min, max=max)


def imagej_description(leading_shape, leading_axes, contrast=None):
    if len(leading_shape) != len(leading_axes):
        error = 'mismatched axes, shape is {} but axis labels are {}'
        raise ValueError(error.format(leading_shape, leading_axes))

    prefix = 'ImageJ=1.49v\n'
    suffix = 'hyperstack=true\nmode=composite\n'
    images = np.prod(leading_shape)
    sizes = {k: v for k,v in zip(leading_axes, leading_shape)}
    description = prefix + 'images={}\n'.format(images)
    if 'C' in sizes:
        description += 'channels={}\n'.format(sizes['C'])
    if 'Z' in sizes:
        description += 'slices={}\n'.format(sizes['Z'])
    if 'T' in sizes:
        description += 'frames={}\n'.format(sizes['T'])
    if contrast is not None:
        min, max = contrast
        description += 'min={0}\nmax={1}\n'.format(min, max)
    description += suffix

    return description


def ij_tag_50838(nchannels):
    """ImageJ uses tag 50838 to indicate size of metadata elements (e.g., 768 bytes per ROI)
    :param nchannels:
    :return:
    """
    info_block = (20,)  # summary of metadata fields
    display_block = (16 * nchannels,)  # display range block
    luts_block = (256 * 3,) * nchannels  #
    return info_block + display_block + luts_block


def ij_tag_50839(luts, display_ranges):
    """ImageJ uses tag 50839 to store metadata. Only range and luts are implemented here.
    :param tuple luts: tuple of 255*3=768 8-bit ints specifying RGB, e.g., constants io.RED etc.
    :param tuple display_ranges: tuple of (min, max) pairs for each channel
    :return:
    """
    d = struct.pack('<' + 'd' * len(display_ranges) * 2, *[y for x in display_ranges for y in x])
    # insert display ranges
    tag = ''.join(['JIJI',
                   'gnar\x01\x00\x00\x00',
                   'stul%s\x00\x00\x00' % chr(len(luts)),
                   ]).encode('ascii') + d
    tag = struct.unpack('<' + 'B' * len(tag), tag)
    return tag + tuple(sum([list(x) for x in luts], []))
    

def load_stitching_offsets(filename):
    """Load i,j coordinates from the text file saved by the Fiji 
    Grid/Collection stitching plugin.
    """
    from ast import literal_eval
    
    with open(filename, 'r') as fh:
        txt = fh.read()
    txt = txt.split('# Define the image coordinates')[1]
    lines = txt.split('\n')
    coordinates = []
    for line in lines:
        parts = line.split(';')
        if len(parts) == 3:
            coordinates += [parts[-1].strip()]
    
    return [(i,j) for j,i in map(literal_eval, coordinates)]