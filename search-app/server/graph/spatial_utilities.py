from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain.prompts import ChatPromptTemplate
from langchain.tools import tool
from typing import Dict, List, Optional
import aiohttp
import asyncio
import json
from app.llm_manager import LLMManager

class SpatialEntity(BaseModel):
    original_query: str = Field(description="Get original query as prompted by the user")
    spatial: str = Field(description="Get the spatial entity. Can be a location or place or a region. Leave empty if nothing is found.")
    scale: str = Field(description="Get the spatial scale. Leave empty if nothing is found")

class LocationResult(BaseModel):
    name: str = Field(description="Name of the selected location")
    country: str = Field(description="Country of the selected location")
    type: str = Field(description="Type of the location (city, river, etc.)")
    extent: List[str] = Field(description="Spatial Extent, i.e. Bounding Box")


# Set up parsers
spatial_context_prompt_parser = JsonOutputParser(pydantic_object=SpatialEntity)

# First prompt to extract spatial context
spatial_context_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert in geography and spatial data. 
    Your task is to extract spatial entities and determine their scale.
    You must respond in the exact JSON format specified, with no additional text."""),
    ("human", """Extract spatial information from this query: {query}
    
    Use these scales: Local, City, Regional, National, Continental, or Global.
    
    Format your response exactly as follows, with no additional text:
    {format_instructions}""")
]).partial(format_instructions=spatial_context_prompt_parser.get_format_instructions())

async def query_osm_async(query_dict: dict) -> Dict:
    """Query OpenStreetMap API"""
    nominatim_url = "https://photon.komoot.io/api"
    query = query_dict['spatial']
    params = {"q": query}
    url = f"{nominatim_url}?q={params['q']}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                results = await response.json()
                simplified_results = [
                    {
                        "name": res["properties"].get("name"),
                        "country": f"{res['properties'].get('country')}",
                        "type": res["properties"].get("type"),
                        "extent": res["properties"].get("extent")
                    }
                    for res in results.get("features", [])
                ]
                return {"results": simplified_results}
            else:
                return {"error": "Failed to query Nominatim"}

def format_location_picker_response(location: Dict) -> Dict[str, str]:
    """Format the location picker response as a spatial context"""
    return {
        "name": location.get("name", ""),
        "country": location.get("country", ""),
        "type": location.get("type", "")
    }

# Second prompt to pick the best location
location_picker_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert in geography and spatial data.
    Your task is to pick the best matching candidate from the results list according to the query.
    Respond with only the selected location details in JSON format."""),
    ("human", """Analyze this spatial query and results to select the best match:
    Scale: {scale}
    Original Query: {original_query}
    Results: {results}
    
    Return only a JSON object with name, country, type and extent (mandatory) of the best matching location.""")
])

def generate_spatial_context_chain(llm):
    spatial_context_chain = (
        spatial_context_prompt
        | llm
        | spatial_context_prompt_parser
        | search_with_osm_query
        | location_picker_prompt
        | llm
        | JsonOutputParser(pydantic_object=LocationResult)
    )
    return spatial_context_chain

@tool
def spatial_context_extraction_tool(query: str):
    """Extract spatial entities, scale and extent from a query"""
    llm = LLMManager.get_llm()
    try:
        # Note: llm should be defined in the outer scope
        chain = generate_spatial_context_chain(llm=llm)
        result = chain.invoke({"query": query})
        
        # Ensure we return a dictionary
        if isinstance(result, str):
            result = json.loads(result)
            
        return result
    except Exception as e:
        return {
            "error": str(e),
            "original_query": query,
            "spatial": "",
            "scale": ""
        }

@tool
def search_with_osm_query(original_query: str, spatial: str, scale: str):
    """Use query and search in osm"""
    if spatial and scale:
        query_dict = {'spatial': spatial, 'scale': scale}
        results = asyncio.run(query_osm_async(query_dict))
    else: 
        results = []
    return {"original_query": original_query, "scale": scale, "results": results}

### Functions to check if results with geojson are within a certain spatial extent
# Use this to check if search results match query bbox.
import json
def is_within_bbox(lon, lat, bbox):
    min_lon, max_lat, max_lon, min_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

def check_within_bbox(search_results, bbox):
    if not bbox:
        return search_results
    
    results_within_bbox = []

    for result in search_results:
        feature_str = result.metadata.get('feature', '{}')
        feature = json.loads(feature_str)
        coordinates = feature.get('coordinates', [])
        
        # Flatten the coordinates (if needed) and check if any coordinate is within the bbox
        for poly in coordinates:
            for coord in poly:  # Assuming polygon with one ring
                lon, lat = coord
                if is_within_bbox(lon, lat, bbox):
                    results_within_bbox.append(result)
                    break  # No need to check other coordinates of this polygon if already within bbox
    
    return results_within_bbox