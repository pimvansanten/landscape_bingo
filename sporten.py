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
from shapely.geometry import Polygon, Point
from shapely.ops import cascaded_union
import geopandas as gpd
import json
from config import *


KIND = sys.argv[1]

SQUARE_SIZE = SETTINGS[KIND][0]
NUM_OF_SQUARES = SETTINGS[KIND][1]

gem = gpd.read_file(
    SHAPE_FOLDER+'cbsgebiedsindelingen_2021_v1.gpkg',
    layer='cbs_gemeente_2020_gegeneraliseerd')
prov = gpd.read_file(
    SHAPE_FOLDER+'cbsgebiedsindelingen_2021_v1.gpkg',
    layer='cbs_provincie_2020_gegeneraliseerd')

gem_utrecht=gem.loc[gem['geometry'].within(prov.loc[6,'geometry'])]
gem_utrecht = gem_utrecht.set_crs(epsg=28992)
gem_utrecht=gem_utrecht.to_crs(epsg=4326)

def get_centroid(index, squares_gdf):
    
    point = squares_gdf.loc[index,'geometry'].centroid
    
    return point.x,point.y
    
def make_center(location):
    jul_gdf = gpd.GeoDataFrame(geometry = gpd.points_from_xy([location[1]],[location[0]], crs = 'epsg:4326'))
    jul_gdf = jul_gdf.to_crs('epsg:28992')
    jul_x = jul_gdf.loc[0].iloc[0].x
    jul_y = jul_gdf.loc[0].iloc[0].y
    
    return jul_x, jul_y

def plot_circles(m,radii, location):
    """plot circles on folium map
    
    m: Folium Map object
    radii: list of int
        cricle radius in m   
    """
    #,15000,20000, 25000, 30000]:
    for r in radii:
        folium.Circle(
            radius=r,
            location=location,
            color='black',
            fill=False,
        ).add_to(m)
        
    return m

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

def load_routes(kind):
    """
    load recorded strava routes
    
    
    kind: string
        should be one of 
        'loop': all running routes
        'cycl': all cycle routes
        '##': double digit integer with leading zero
              for all routes to that circle
    """
    if len(kind)==4:
        condition =f"name.split('.')[0][:4] == '{kind}'"
    else:
        condition = f"name.split('.')[0][-2:] =={kind}"
    
    try:
        with open(f'routes_{KIND}.json', 'r') as myfile:
            data=myfile.read()
        # parse file
        routes_dict = json.loads(data)
    except:
        routes_dict={}
        
#    routes_dict={}
    punt_shapes = []
    new_routes=[]
    for root, dirs, files in os.walk(GPX_FOLDER):
       for name in files:
           if eval(condition):
               if name not in routes_dict.keys():
                   print(name)
                   new_routes.append(name)
                   soort,date,dist = name.split('_')
                   dist = dist[:2]
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
                   routes_dict[name]['circle'] = dist

    gdf_all_points = gpd.GeoDataFrame(geometry = punt_shapes)
    
    return gdf_all_points, routes_dict, new_routes

def plot_routes(m, routes, routes_dict):
    kleuren = {
        '00':'blue',
        '25':'lightseagreen',
        '20':'olive',
        '15':'red',
        '03':'blue'}
    
    for route in routes:
        folium.PolyLine(routes_dict[route]['punten'],
                        color=kleuren[routes_dict[route]['circle']],
                        tooltip = routes_dict[route]['date'],
                        ).add_to(m)

    return m

def find_filled_squares(squares_gdf, routes_gdf):
    
    nos=NUM_OF_SQUARES
    #create indices starting at middle column and then working sideways
    #this helps losing many points fast
    inds = np.concatenate(
            [k+np.arange(2*nos) for k in 
             [j*2*nos for sublist in 
              [[nos-i,nos+i] for i in range(nos)] 
              for j in sublist
              ][1:]
             ]
             ) 
    
    squares_gdf['new']=False
    for index in inds:
        square = squares_gdf.loc[index]
        if not square['filled']:
            points_within=routes_gdf.within(square['geometry'])
            if any(points_within):
                squares_gdf.at[index,'filled'] = True
                squares_gdf.at[index,'new'] = True
                #delete points in filled squares for speeding up process
                routes_gdf=routes_gdf.drop(
                    routes_gdf.loc[points_within].index)
    
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

    for index,poly in gem_utrecht.iterrows():
        folium.Polygon([(j,i) for i,j in [point for polygon in poly['geometry'] for point in polygon.exterior.coords[:-1]]],
                        weight = 0.6,
                        fill=False,
                        color='green',
                        tooltip=poly['statnaam']).add_to(m)
    return m


def plot_big_square(m, squares_gdf):
    
    big_square = cascaded_union(list(squares_gdf.loc[squares_gdf['big_square']==1]['geometry']))
    folium.Polygon([(j,i) for i,j in list(big_square.exterior.coords)],
                    weight = 1,
                    color = '#ff0000',
                    ).add_to(m)
    return m


#flow
cent_x, cent_y = make_center(LOCATIONS[LOC])
if INIT:
    squares_gdf = make_squares(SQUARE_SIZE, NUM_OF_SQUARES, cent_x, cent_y)
else:
    squares_gdf=read_squares_from_file(KIND)
gdf_all_points, routes_dict, new_routes = load_routes(KIND)
print('find filled squares')
squares_gdf = find_filled_squares(squares_gdf,gdf_all_points)
squares_gdf = fill_unreachables(squares_gdf, UNREACHABLES, KIND)
squares_gdf = create_big_square(NUM_OF_SQUARES, squares_gdf)
m = folium.Map(location=LOCATIONS[LOC], zoom_start=12)
m = plot_all_squares(m,squares_gdf)
m=plot_routes(m,new_routes, routes_dict)
m = plot_big_square(m,squares_gdf)
m=plot_gem(m,gem_utrecht)
m.save(f'squares_{KIND}_{LOC}.html')
# m.save('testgemn.html')
squares_gdf.to_feather(f'squares_gdf_{KIND}.feather')
with open(f'routes_{KIND}.json', 'w') as f:
    json.dump(routes_dict, f)


