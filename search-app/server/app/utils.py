import os 
import json
from pathlib import Path
from loguru import logger
from graph.graph import SpatialRetrieverGraph

from config.config import resolve_abs_path


class SessionData():
    def __init__(self, session_id: str, graph: SpatialRetrieverGraph):
        self.session_id = session_id
        self.graph = graph
    

### Geojson utilities
def calculate_bounding_box(geojson):
    min_lng, min_lat = float('inf'), float('inf')
    max_lng, max_lat = float('-inf'), float('-inf')
    
    def extract_coordinates(geometry):
        if geometry['type'] == 'Point':
            return [geometry['coordinates']]
        elif geometry['type'] in ['MultiPoint', 'LineString']:
            return geometry['coordinates']
        elif geometry['type'] in ['MultiLineString', 'Polygon']:
            return [coord for line in geometry['coordinates'] for coord in line]
        elif geometry['type'] == 'MultiPolygon':
            return [coord for poly in geometry['coordinates'] for line in poly for coord in line]
        else:
            return []

    for feature in geojson['features']:
        coords = extract_coordinates(feature['geometry'])
        for coord in coords:
            lng, lat = coord
            min_lng = min(min_lng, lng)
            min_lat = min(min_lat, lat)
            max_lng = max(max_lng, lng)
            max_lat = max(max_lat, lat)

    return [min_lng, min_lat, max_lng, max_lat]


def summarize_feature_collection_properties(feature_collection):

    data = list(map(lambda f: f['properties'], feature_collection['features']))

    summary = {}
    
    for item in data:
        item_type = item.get('type', '')
        description = item.get('description', '')
        
        if item_type not in summary:
            summary[item_type] = {'count': 0, 'descriptions': []}
        
        summary[item_type]['count'] += 1
        
        if description and description not in summary[item_type]['descriptions']:
            summary[item_type]['descriptions'].append(description)
    
    summary_text = ""
    for item_type, details in summary.items():
        summary_text += f"Type: {item_type} (Count: {details['count']})\nDescriptions:\n"
        for desc in details['descriptions']:
            summary_text += f"- {desc}\n"
        summary_text += "\n"
    
    return summary_text.strip()


### Custom prompt utilities

def save_conversational_prompts(file_name, conversational_prompts):
    with open(file_name, 'w') as f:
        json.dump(conversational_prompts, f, indent=4)  # Pretty print with indentation


def read_dict_from_module(module_path):
    module_name = Path(module_path).stem
    if os.path.exists(f"{module_path}"):
        try:
            from graph.custom_prompts.custom_prompts import prompts  
            return prompts
        except ImportError:
            logger.exception("Error importing custom prompts!")
            return None
    else:
        logger.info(f"Module '{module_name}.py' does not exist.")
        return None

def write_dict_to_file(dictionary, filename):
    with open(filename, 'w') as file:
        file.write(f"prompts = {repr(dictionary)}\n")

def load_conversational_prompts(collection_router):
    custom_prompts_path = resolve_abs_path('./graph/custom_prompts/custom_prompts.py')
    loaded_dict = read_dict_from_module(custom_prompts_path)
    if not collection_router.coll_dicts:
        logger.info("No collections in vector store. Not generating individual prompts")
        return {}

    collection_names = [c['collection_name'] for c in collection_router.coll_dicts]

    if loaded_dict and set(loaded_dict.keys()) == set(collection_names):
        logger.info("Custom prompts already generated for current collections. Reading it from file...")
        conversational_prompts = loaded_dict
    else:   
        conversational_prompts = collection_router.generate_conversation_prompts()
        write_dict_to_file(conversational_prompts, custom_prompts_path)
    
    return conversational_prompts


