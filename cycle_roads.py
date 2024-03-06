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
    if len(kind)==4:
        condition =f"name.split('.')[0][:4] == '{kind}'"
    else:
        condition = f"name.split('.')[0][-2:] =={kind}"
    
    if INIT:
        routes_dict={}
    else:
        try:
            with open(f'routes_{KIND}.json', 'r') as myfile:
                data=myfile.read()
            # parse file
            routes_dict = json.loads(data)
        except:
            routes_dict={}
        
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

def plot_routes(m, new_routes, routes_dict):
    
    for naam, route in routes_dict.items():
        if naam in new_routes:
            color="red"
        else:
            color="blue"
        folium.PolyLine(route['punten'],
                        color=color,
                        tooltip = route['date'],
                        ).add_to(m)

    return m

KIND = "cycl"
INIT = False


gdf_all_points, routes_dict, new_routes = load_routes(KIND, INIT)
m = folium.Map(location=LOCATIONS[LOC], zoom_start=12)
m = plot_routes(m,new_routes, routes_dict)
m.save(f'routes_{KIND}_{LOC}.html')
with open(f'routes_{KIND}.json', 'w') as f:
    json.dump(routes_dict, f)
print('Done')


