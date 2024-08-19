from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain.prompts import PromptTemplate
from langchain.tools import tool
import aiohttp
import asyncio
import nest_asyncio

# Allow nested asyncio.run calls
nest_asyncio.apply()

# Define your desired data structure.
class SpatialEntity(BaseModel):
    original_query: str = Field(description="Get original query as prompted by the user")
    spatial: str = Field(description="Get the spatial entity. Can be a location or place or a region")
    scale: str = Field(description="Get the spatial scale")

# Set up a parser + inject instructions into the prompt template.
spatial_context_prompt_parser = JsonOutputParser(pydantic_object=SpatialEntity)

spatial_context_prompt = PromptTemplate(
    template="""
    You are an expert in geography and spatial data. 
    Your task is to extract from a query spatial entities such as city, country or region names.
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
    query_dict = {'spatial': spatial, 'scale': scale}
    results = asyncio.run(query_osm_async(query_dict))
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


# response = spatial_context_chain.invoke({"query": "I climate data for Berlin"})
# print(response)
