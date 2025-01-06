from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain.prompts import PromptTemplate
from langchain.tools import tool
import aiohttp
import asyncio


# Define your desired data structure.
class SpatialEntity(BaseModel):
    original_query: str = Field(description="Get original query as prompted by the user")
    spatial: str = Field(description="Get the spatial entity. Can be a location or place or a region. Leave empty if nothing is found.")
    scale: str = Field(description="Get the spatial scale. Leave empty if nothing is found")

# Set up a parser + inject instructions into the prompt template.
spatial_context_prompt_parser = JsonOutputParser(pydantic_object=SpatialEntity)

spatial_context_prompt = PromptTemplate(
    template="""
    You are an expert in geography and spatial data. 
    Your task is to extract from a query spatial entities such as city, country or region names (if possible).
    Also determine the spatial scale ("Local", "City", "Regional", "National", "Continental", "Global") from the given query.

    Output:{format_instructions}\n{query}\n""",
    input_variables=["query"],
    partial_variables={"format_instructions": spatial_context_prompt_parser.get_format_instructions()},
)

async def query_osm_async(query_dict: dict):
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
@tool
def search_with_osm_query(original_query: str, spatial: str, scale: str):
    """
    Use query and search in osm
    """
    if spatial and scale:
        query_dict = {'spatial': spatial, 'scale': scale}
        results = asyncio.run(query_osm_async(query_dict))
    else: 
        results = []
    return {"original_query": original_query, "scale": scale, "results": results}

osm_picker_prompt = PromptTemplate(
    template="""
    You are an expert in geography and spatial data. 
    Your task is to pick from the results list the best matching candidate according to the query.
    If the original query includes a country information, consider this in your selection.
    If also consider the type. E.g. if user asks for a 'river' also pick the corresponding result

    Also consider the scale: {scale}
    Query: {original_query}
    Results: {results}
    Output:""",
    input_variables=["original_query", "scale", "results"],
)

def generate_spatial_context_chain(llm):
    spatial_context_chain = (
        spatial_context_prompt
        | llm
        | spatial_context_prompt_parser
        | search_with_osm_query
        | osm_picker_prompt
        | llm
    )
    return spatial_context_chain


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
