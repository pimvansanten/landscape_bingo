
# -*- coding: utf-8 -*-
"""
Created on Sun Jan 26 16:05:01 2020

@author: santpi01
"""

import sys
import numpy as np
import folium
import gpxpy
import os
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import cascaded_union
from shapely import convex_hull
import geopandas as gpd
import json
from config import *
import copy


KIND = sys.argv[1]
if KIND.endswith('json'):
    KIND = "cycl"

SQUARE_SIZE = SETTINGS[KIND][0]
NUM_OF_SQUARES = SETTINGS[KIND][1]
CENT_SQUARE = 45150

# gem = gpd.read_file(
#     SHAPE_FOLDER+'cbsgebiedsindelingen_2021_v1.gpkg',
#     layer='cbs_gemeente_2020_gegeneraliseerd')
# prov = gpd.read_file(
#     SHAPE_FOLDER+'cbsgebiedsindelingen_2021_v1.gpkg',
#     layer='cbs_provincie_2020_gegeneraliseerd')

# gem_utrecht=gem.loc[gem['geometry'].within(prov.loc[6,'geometry'])]
# gem_utrecht = gem_utrecht.set_crs(epsg=28992)
# gem_utrecht=gem_utrecht.to_crs(epsg=4326)

def get_centroid(index, squares_gdf):
    
    point = squares_gdf.loc[index,'geometry'].centroid
    
    return point.x,point.y
    
def make_center(location):
    jul_gdf = gpd.GeoDataFrame(
        geometry = gpd.points_from_xy(
            [location[1]],[location[0]],
            crs = 'epsg:4326')
        )
    jul_gdf = jul_gdf.to_crs('epsg:28992')
    jul_x = jul_gdf.loc[0].iloc[0].x
    jul_y = jul_gdf.loc[0].iloc[0].y
    
    return jul_x, jul_y

def get_nl():
    gpx_file = open(GPX_FOLDER+"NL-omtrek.gpx", 'r')
    gpx = gpxpy.parse(gpx_file)
    gpx_file.close()
    punt_shapes = []
    
    for track in gpx.tracks:
        for segment in track.segments:
            
            punt_shapes = punt_shapes + [
                Point(point.longitude, point.latitude)
                for point in segment.points]
    nl = Polygon(punt_shapes)

    return nl

def make_squares(size, num, x_center, y_center):
    
    sqsz = size 
    numofsq = num
    polygons = []
    for x in range(-numofsq*sqsz,numofsq*sqsz,sqsz):
        for y in range(-numofsq*sqsz,numofsq*sqsz,sqsz):
            polygons.append(Polygon([(x_center+x,y_center+y),
                                     (x_center+x+sqsz,y_center+y),
                                     (x_center+x+sqsz,y_center+y+sqsz),
                                     (x_center+x,y_center+y+sqsz)]))
            
    
    squares_gdf = gpd.GeoDataFrame(geometry = polygons)
    squares_gdf = squares_gdf.set_crs('epsg:28992')
    squares_gdf = squares_gdf.to_crs('epsg:4326')
    squares_gdf['filled'] = False
    
    return squares_gdf

def read_squares_from_file(KIND):
    squares_gdf = gpd.read_feather(f'squares_gdf_{KIND}.feather')
    return squares_gdf

def load_routes(kind, INIT):
    """
    load recorded strava routes
    
    
    kind: string
        should be one of 
        'loop': all running routes
        'cycl': all cycle routes
        '##': double digit integer with leading zero
              for all routes to that circle
    """

    condition =f"name.split('.')[0][:4] == '{kind}'"
    
    if INIT:
        routes_dict={}
    else:
        with open(f'routes_{KIND}.json', 'r') as myfile:
            data=myfile.read()
        # parse file
        routes_dict = json.loads(data)
        
    punt_shapes = []
    new_routes=[]
    for root, _, files in os.walk(GPX_FOLDER):
       for name in files:
           if eval(condition):
               if name not in routes_dict.keys():
                   print(name)
                   new_routes.append(name)
                   delen = name.split('_')
                   soort = delen[0]
                   date = delen[1]
                   gpx_file = open(os.path.join(root, name), 'r')
                   gpx = gpxpy.parse(gpx_file)
                   gpx_file.close()
                   punten = []
                   
                   for track in gpx.tracks:
                       for segment in track.segments:
                           punten = punten + [(point.latitude, point.longitude) for point in segment.points]
                           punt_shapes = punt_shapes + [Point(point.longitude, point.latitude) for point in segment.points]
                   routes_dict[name] = {}
                   routes_dict[name]['punten'] = punten
                   routes_dict[name]['soort'] = soort
                   routes_dict[name]['date'] = date

    gdf_all_points = gpd.GeoDataFrame(geometry = punt_shapes)
    
    return gdf_all_points, routes_dict, new_routes

def plot_routes(m, routes, routes_dict):
    
    for route in routes:
        folium.PolyLine(routes_dict[route]['punten'],
                        color='blue',
                        tooltip = routes_dict[route]['date'],
                        ).add_to(m)

    return m


def find_filled_squares2(squares_gdf, points_gdf):
    
    squares_gdf['new'] = False
    filled_squares_all = squares_gdf[~squares_gdf["filled"]].sjoin(
        gdf_all_points, how="left").dropna(subset="index_right")
    filled_squares = filled_squares_all.groupby(
        filled_squares_all.index).first()
    
    squares_gdf.loc[filled_squares.index, 'filled'] = True
    squares_gdf.loc[filled_squares.index, 'new'] = True
    
    return squares_gdf


def fill_unreachables(squares_gdf, locs, kind):
    
    squares_gdf['unreach']=False
    indices={}
    for naam,_ in SETTINGS.items():
        if naam in locs.keys():
            indices[naam]=locs[naam]
        else:
            indices[naam]={}
    for punt in list(indices[kind].keys()):
        squares_gdf.loc[
            squares_gdf['geometry'].contains(Point(punt)),
            'unreach'] = True
        squares_gdf.loc[
            squares_gdf['geometry'].contains(Point(punt)),
            'filled'] = True
    
    return squares_gdf

def create_big_square(sq_num, squares_gdf):
    cols = rows = int(2*NUM_OF_SQUARES)
    big_square = np.zeros((rows,cols))
    filled_squares=np.flipud(
        squares_gdf['filled'].values\
            .astype(int)\
                .reshape(rows,cols)\
                    .T)
    
    n=2
    cel={}
    gadoor=True
    while gadoor:
        i=0
        cel[n]=[]
        for r in range(rows-n):
            for c in range(cols-n):
                if np.all(filled_squares[r:r+n,c:c+n]==1):
                    i+=1
                    cel[n].append((r,c))
        if i>0:
            n+=1
        else:
            gadoor=False
            n=n-1
    
    r = cel[n][0][0]
    c = cel[n][0][1]
    big_square[r:r+n,c:c+n]=1
    big_square_array = np.flipud(big_square).T.flatten()
    squares_gdf['big_square'] = big_square_array
    print(f'je vierkant is nu {n}x{n} groot')
    return squares_gdf


def create_big_square2(squares_gdf):
    i = [CENT_SQUARE]
    j = 1
    nsq = 2*NUM_OF_SQUARES
    while squares_gdf.loc[i, "filled"].all():
        j+=2
        k = list(range(-j//2+1,j//2+1))
        m = [CENT_SQUARE+nsq*l for l in k]
        i = [q+p for p in m for q in k]
    # j is now 1 g=bigger than a potential filled big square
    # find this
    big_square = squares_gdf.loc[i, "filled"].copy()
    missing = big_square.loc[~big_square].index
    #indices of all sides
    w = np.arange(21) + big_square.index.min()
    e = big_square.index.max() - np.arange(21)
    s = np.arange(w.min(), e.min()+nsq, nsq)
    n = np.arange(w.max(), e.max()+nsq, nsq)
    # which sides have missing squares
    mis_sides = []
    for cd in ["w", "e","n", "s"]:
        exec(f"{cd}pr = any([i in {cd} for i in missing])")
        exec(f"if {cd}pr: mis_sides.extend(list({cd}))")
    if (wpr and epr) or (npr and spr):
        # on both sides so no even number possible
        bss = j-2
        i = [q for q in i if q not in np.concatenate([w, e, n, s])]
    else:
        bss = j-1
        i = [q for q in i if q not in mis_sides]
        if len(missing)==1:
            if wpr or epr:
                i = [q for q in i if q not in s]
            if npr or spr:
                i = [q for q in i if q not in e]
    squares_gdf['big_square'] = False
    squares_gdf.loc[i, 'big_square'] = True

    return squares_gdf


def plot_all_squares(m,squares_gdf):
    #filled squares
    for index,square in squares_gdf.loc[squares_gdf['filled']].iterrows():
        folium.Polygon([(j,i) for i,j in list(square['geometry'].exterior.coords)],
                        weight = 0.3,
                        fill=True,
                        fillOpacity=0.6,
                        tooltip=str(index)).add_to(m)
    #not filled squares
    for index,square in squares_gdf.loc[~squares_gdf['filled']].iterrows():
        folium.Polygon([(j,i) for i,j in list(square['geometry'].exterior.coords)],
                        color = 'gray',
                        weight = 0.3).add_to(m)  
    
    #newly filled squares  
    try:
        for index,square in squares_gdf.loc[squares_gdf['new']].iterrows():
            folium.Polygon([(j,i) for i,j in list(square['geometry'].exterior.coords)],
                            weight = 0.3,
                            fill=True,
                            color='red',
                            fillOpacity=0.6,
                            tooltip=str(index)).add_to(m)
    except:
        pass
    
    try:
        for index,square in squares_gdf.loc[squares_gdf['unreach']].iterrows():
            folium.Polygon([(j,i) for i,j in list(square['geometry'].exterior.coords)],
                            weight = 0.3,
                            fill=True,
                            color='magenta',
                            fillOpacity=0.6,
                            tooltip=str(index)).add_to(m)
    except:
        pass
            
    return m

def plot_gem(m,gem):

    4326
    return m


def plot_big_square(m, squares_gdf):
    
    big_square = cascaded_union(list(squares_gdf.loc[squares_gdf['big_square']]['geometry']))
    folium.Polygon([(j,i) for i,j in list(big_square.exterior.coords)],
                    weight = 1,
                    color = '#ff0000',
                    ).add_to(m)
    return m


def plot_goal(m):

    goal_rect = convex_hull(MultiPolygon(list(squares_gdf.loc[
        [40634, 40667, 52067, 52034],
        'geometry'])))
    folium.Polygon([(j,i) for i,j in list(goal_rect.exterior.coords)],
                weight = 1,
                color = '#00ff00',
                ).add_to(m)
    return m
    


#flow
cent_x, cent_y = make_center(LOCATIONS[LOC])
if INIT:
    squares_gdf = make_squares(
        SQUARE_SIZE, NUM_OF_SQUARES, cent_x, cent_y)
    nl = get_nl()
    squares_gdf = squares_gdf[
        squares_gdf["geometry"].within(nl)].copy()
else:
    squares_gdf=read_squares_from_file(KIND)
gdf_all_points, routes_dict, new_routes = load_routes(KIND, INIT)
print('find filled squares')
squares_gdf = find_filled_squares2(squares_gdf,gdf_all_points)
squares_gdf = fill_unreachables(squares_gdf, UNREACHABLES, KIND)
squares_gdf = create_big_square2(squares_gdf)
m = folium.Map(location=LOCATIONS[LOC], zoom_start=10)
m = plot_all_squares(m,squares_gdf)
m = plot_routes(m,new_routes, routes_dict)

m_all = folium.Map(location=LOCATIONS[LOC], zoom_start=12)
m_all = plot_all_squares(m_all,squares_gdf)
m_all = plot_routes(m_all,routes_dict.keys(), routes_dict)
m = plot_big_square(m,squares_gdf)
# m=plot_gem(m,gem_utrecht)
m = plot_goal(m)

folium.raster_layers.WmsTileLayer(
    url="https://service.pdok.nl/cbs/gebiedsindelingen/2023/wms/v1_0?request=GetCapabilities&service=WMS",
    name="test",
    fmt="image/png",
    layers="cbs_gemeente_2023_gegeneraliseerd",
    transparent=True,
    overlay=True,
    control=True,
).add_to(m)

m.save(f'squares_{KIND}_{LOC}.html')
m_all.save(f'squares_{KIND}_{LOC}_all.html')
# m.save('testgemn.html')
squares_gdf.to_feather(f'squares_gdf_{KIND}.feather')
with open(f'routes_{KIND}.json', 'w') as f:
    json.dump(routes_dict, f)
print('Done')
