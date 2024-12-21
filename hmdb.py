#!/usr/bin/env python
# coding: utf-8

import requests
import pandas as pd
from datetime import datetime
import json


def read_atlas(filename):
    """
    Imports the main atlas csv file into a dataframe
    """
    
    types = {'ref:US-TX:thc':'Int32', 'ref:hmdb':'Int32', 'start_date':'Int32',
             'UTM Easting':'Int32', 'UTM Northing':'Int32', 
             'UTM Zone':'Int16', 
             'isTHC':'boolean', 'isHMDB':'boolean','isOSM':'boolean', 'isMissing':'boolean', 
             'isPending':'boolean', 'Recorded Texas Historic Landmark':'boolean', 
             'Private Property':'boolean',
             'inGoogle':'boolean'}

    atlas = pd.read_csv(filename, dtype=types, low_memory=False)
    return atlas

def create_nodes(df):
    """
    Create OSM nodes from a dataframe.
    
    Parameters:
        df (dataframe):  The marker dataframe (typically a subset) that contains the information to create OSM nodes from.

    Returns:
        nodes (list): A list formatted with key:value pairs formatted for import into JOSM.
    """    
    nodes = []
    for index, row in df.iterrows():
        try:
            # Extract information
            name = row["name"]
            start_date = row["start_date"]
            ref_thc = row["ref:US-TX:thc"]
            website = row["website"]
            lat = row["hmdb:Latitude"]
            lon = row["hmdb:Longitude"]
            ref_hmdb = row["ref:hmdb"]
            
            tags = {"name":name, 
                    "historic":"memorial",
                    "memorial":"plaque",
                    "material":"aluminium",
                    "support":"pole",
                    "operator":"Texas Historical Commission",
                    "operator:wikidata":"Q2397965",
                    "thc:designation":"Historical Marker",
                    "start_date":start_date,
                    "ref:US-TX:thc":ref_thc,
                    "ref:hmdb":ref_hmdb,
                    "source:website":website,
                    "memorial:website":"https://www.hmdb.org/m.asp?m="+str(ref_hmdb)                    
                   }

            # Create a node
            nodes.append({"lat":lat, "lon":lon, "tags":tags})
            
        except Exception as e:
            print(f"Failed to create node for row {index}: {e}")
            
    return nodes

def push2josm(nodes):

    # JOSM Remote Control URL
    josm_url = "http://localhost:8111/add_node"
    
    updated_nodes = []
    count = 0    
    
    for node in nodes:
        params = {
            "lat": node["lat"],
            "lon": node["lon"],
        }
        tags = ""
        for key, value in node["tags"].items():
            tags=tags+str(key)+"="+str(value)+"|"

        params["addtags"] = tags[:-1]  

        # Send the request
        response = requests.get(josm_url, params=params)
        if response.status_code == 200:
            updated_nodes.append(node["tags"]["ref:US-TX:thc"])
            count = count + 1
        else:
            print(f"Failed to add node at ({node['lat']}, {node['lon']}). Status code: {response.status_code}")
            
    print(f"Completed pushing {count} nodes to JOSM")
    
    return updated_nodes

def write2csv(df, filename, date=False):
    """
    Write out the dataframe back out into a csv file.

    Parameters:
            df  (dataframe): The atlas database that has been modified.
            filename  (string):  The csv filename. For now it assumes to write in the current directory.
            date (boolean): An optional value. If it exists then the current data is prepended to the file name. This is useful for creating archivable file versions.
    """            
    if date: filename = "./file_backup/"+str(datetime.now().strftime('%Y%m%d'))+"_"+filename
        
    try:
        # Write the DataFrame to a CSV file
        df.to_csv(filename, index=False)
        print(f"{filename} written to disk.")
        return 

    except:
        print("Error has occured in 'write2csv()' function")
        return 


def find_missing_osm(atlas, geojson):
    ## Compare refs ##

    # Load the GeoJSON file
    with open(geojson,'r') as file:
        geojson_data = json.load(file)

    # Extract refs from the GeoJSON features
    geojson_refs = {int(feature['properties']['ref:US-TX:thc']) for feature in geojson_data.get('features', []) if 'ref:US-TX:thc' in feature['properties']}

    # Check for matches
    #matching_refs = atlas[atlas['ref:US-TX:thc'].isin(geojson_refs)]
    matching_refs = list(geojson_refs.intersection(filtered_df['ref:US-TX:thc']))

    # Display the matching rows
    if matching_refs:
        print(f"{len(updated_nodes)} matching thc-refs found.")
        return matching_refs 
    else:
        print("No matching refs found.")
        return 
    
def update_db(updated_nodes, atlas):
    before = len(atlas.loc[atlas['isOSM'] == True])
    for ref in updated_nodes:
        atlas.loc[atlas['ref:US-TX:thc'] == ref, 'isOSM'] = True
    after = len(atlas.loc[atlas['isOSM'] == True])
    print(f"{after-before} fields were updated")
    return atlas