import string
import re
import numpy as np
import pandas as pd


def add_global_xy(df, well_spacing, grid_shape, grid_spacing='10X', factor=1.):
    """Adds global x and y coordinates to a dataframe with 
    columns indicating (i, j) or (x, y) positions. 
    """
    
    df = df.copy()
    wt = list(zip(df['well'], df['tile']))
    d = {(w,t): plate_coordinate(w, t, well_spacing, grid_spacing, grid_shape) for w,t in set(wt)}
    y, x = zip(*[d[k] for k in wt])

    if 'x' in df:
        df['global_x'] = x + df['x'] * factor
        df['global_y'] = y + df['y'] * factor
    elif 'i' in df:
        df['global_x'] = x + df['j'] * factor
        df['global_y'] = y + df['i'] * factor
    else:
        df['global_x'] = x
        df['global_y'] = y

    df['global_y'] *= -1
    return df


def plate_coordinate(well, tile, well_spacing, grid_spacing, grid_shape):
    """Returns global plate coordinate (i,j) in microns for a tile in a well. 
    The position is based on:
    `well_spacing` microns
      or one of '96w', '24w', '6w' for standard well plates 
    `grid_spacing` microns
      or one of '10X', '20X' for common spacing at a given magnification
    `grid_shape` (# rows, # columns)  
    """
    tile = int(tile)
    if well_spacing.upper() == '96W':
        well_spacing = 9000
    elif well_spacing.upper() == '24W':
        well_spacing = 19300
    elif well_spacing.upper() == '6W':
        well_spacing = 39120
        
    # common spacings
    if str(grid_spacing).upper() == '10X':
        delta = 1280
    elif str(grid_spacing).upper() == '20X':
        delta = 640
    else:
        delta = grid_spacing

    row, col = well_to_row_col(well, mit=True)
    i, j = row * well_spacing, col * well_spacing

    height, width = grid_shape
    i += delta * int(tile / width)
    j += delta * (tile % width)
    
    i -= delta * ((height - 1) / 2.) 
    j -= delta * ((width  - 1)  / 2.)

    return i, j


def add_row_col(df, well='well', mit=False):
    rows, cols = zip(*[well_to_row_col(w, mit=mit) for w in df[well]])
    return df.assign(row=rows, col=cols)


def well_to_row_col(well, mit=False):
    if mit:
        return string.ascii_uppercase.index(well[0]), int(well[1:]) - 1
    else:
        return well[0], int(well[1:])


def standardize_well(df, col='well'):
    """Sane well labels.
    """
    arr = ['{0}{1:02d}'.format(w[0], int(w[1:])) for w in df[col]]
    return df.assign(**{col: arr})


def remap_snake(site, grid_shape):
    """Maps site names from snake order (Micro-Manager HCS plugin) 
    to row order.
    """

    rows, cols = grid_shape
    grid = np.arange(rows*cols).reshape(rows, cols)
    grid[1::2] = grid[1::2, ::-1]
    site_ = grid.flat[int(site)]
    return '%d' % site_


def filter_micromanager_positions(filename, well_site_list):
    """Restrict micromanager position list to given wells and sites.
    """
    import json
    if isinstance(well_site_list, pd.DataFrame):
        well_site_list = zip(well_site_list['well'], well_site_list['site'])

    well_site_list = set((str(w), str(s)) for w,s in well_site_list)
    def filter_well_site(position):
        pat = '(.\d+)-Site_(\d+)'
        return re.findall(pat, position['LABEL'])[0] in well_site_list
    
    with open(filename, 'r') as fh:
        d = json.load(fh)
        print ('read %d positions from %s' % (len(d['POSITIONS']), filename))
    
    d['POSITIONS'] = list(filter(filter_well_site, d['POSITIONS']))
    
    import datetime
    timestamp = '{date:%Y%m%d_%I.%M%p}'.format( date=datetime.datetime.now() )
    filename2 = '%s.%s.filtered.pos' % (filename, timestamp)
    with open(filename2, 'w') as fh:
        json.dump(d, fh)
        print( '...')
        print ('wrote %d positions to %s' % (len(d['POSITIONS']), filename2))
