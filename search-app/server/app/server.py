from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from langserve import add_routes
from graph.graph import SpatialRetrieverGraph, State
from graph.routers import CollectionRouter
from config.config import Config
from indexing.indexer import Indexer
from connectors.pygeoapi_retriever import PyGeoAPI
from connectors.geojson_osm import GeoJSON
from langchain.schema import Document
from langchain_core.messages import HumanMessage
from fastapi.middleware.cors import CORSMiddleware
from .utils import (SessionData, cookie, verifier, backend, 
                    calculate_bounding_box, summarize_feature_collection_properties, 
                    load_conversational_prompts)

from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from fastapi import HTTPException, FastAPI, Depends, Response, Security
from fastapi.security.api_key import APIKeyHeader, APIKey
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from uuid import UUID, uuid4
from typing import List
import geojson
from pydantic import BaseModel
import json
import logging


logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


# Define the origins that should be allowed to make requests to your API
origins = [
    "http://localhost:5173",  # Frontend app origin
]

# Init memory:
memory = AsyncSqliteSaver.from_conn_string(":memory:")

### Get session info via cookie
async def get_current_session(session_id: UUID = Depends(cookie), session_data: SessionData = Depends(verifier)):
    return session_data

config = Config('./config/config.json')

#Authentificate
API_KEY = config.sdsa_api_key  # Replace with your actual API key
API_KEY_NAME = "X-API-Key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


# Init graph-app
# graph = SpatialRetrieverGraph(State(messages=[], search_criteria="", search_results=[], ready_to_retrieve="")).compile()
graph = None
session_id = None


# Create a dictionary of indexes
indexes = {
    "pygeoapi": Indexer(index_name="pygeoapi",
                        score_treshold= 0.4,
                        k = 20),
    "geojson_osm_indexer": Indexer(index_name="geojson", # Add indexer for local geojson with OSM features
                             score_treshold=-400.0, 
                             k = 20,
                             use_hf_model=True,
                             embedding_model="Alibaba-NLP/gte-large-en-v1.5"
                            )
}

# Add connection to local file including building features 
# Replace the value for tag_name argument if you have other data 
geojson_osm_connector = GeoJSON(tag_name="building")
"""
# We can also use a osm/geojson that comes from a web resource
local_file_connector = GeoJSON(file_dir="https://webais.demo.52north.org/pygeoapi/collections/dresden_buildings/items",
                               tag_name="building")
"""

# Adding conversational routes. We do this here to avoid time-expensive llm calls during inference:
collection_router = CollectionRouter()

# Check if already custom prompts generated and if yes: check if these match the existing search indexes 
conversational_prompts = load_conversational_prompts(collection_router=collection_router)



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(status_code=403, detail="Could not validate API Key")

@app.get("/")
async def redirect_root_to_docs():
    return RedirectResponse("/docs")

### Get session info via cookie
async def get_current_session(session_id: UUID = Depends(cookie), session_data: SessionData = Depends(verifier)):
    return session_data

@app.get("/whoami", dependencies=[Depends(cookie)])
async def whoami(session_data: SessionData = Depends(get_current_session)):
    return session_data

@app.post("/delete_session")
async def del_session(response: Response, session_id: UUID = Depends(cookie)):
    await backend.delete(session_id)
    cookie.delete_from_response(response)
    return "deleted session"

@app.post("/create_session")
async def create_session(response: Response):
    session = uuid4()
    session_id = str(session)

    global graph

    graph = SpatialRetrieverGraph(state=State(messages=[], 
                                              search_criteria="", 
                                              spatial_context="",
                                              search_results=[], 
                                              ready_to_retrieve=""), 
                                              thread_id=session_id, 
                                              memory=memory,
                                              search_indexes=indexes,
                                              collection_router=collection_router,
                                              conversational_prompts=conversational_prompts
                                              ).compile()

    data = SessionData(session_id=session_id)

    await backend.create(session, data)
    cookie.attach_to_response(response, session)

    return {"message": f"created session for {session}"}

class Query(BaseModel):
    query: str
    
@app.post("/data")
async def call_graph(query_data: Query, session_id: UUID = Depends(cookie)):
    if graph is not None:
        print(f"-#-#--Running graph---- Using session_id: {str(session_id)}")
        inputs = {"messages": [HumanMessage(content=query_data.query)]}
        graph.graph.thread_id = str(session_id)
        response = await graph.ainvoke(inputs)
    else:
        raise HTTPException(status_code=400, detail="No session created")
    return response

@app.get("/fetch_documents")
async def fetch_documents(indexing: bool=True, api_key: APIKey = Depends(get_api_key)):
    docs_to_index = []
    
    # Scrape from pygeoapi resources
    pygeoapi = PyGeoAPI()
    pygeoapi_docs = await pygeoapi.get_docs_for_all_instances()
    logging.info(f"Retrieved {len(pygeoapi_docs)} documents from pygeoapi")
        
    if indexing:
        # Indexing received docs
        logging.info("Indexing fetched documents in pygeoapi index")
        res_pygeoapi = indexes["pygeoapi"]._index(documents=pygeoapi_docs)
    
    return {'indexing_results': {
        'pygeoapi': res_pygeoapi,
        }
    }

@app.get("/index_geojson_osm_features")
async def index_geojson_osm(api_key: APIKey = Depends(get_api_key)):
    # await local_file_connector.add_descriptions_to_features()
    feature_docs = await geojson_osm_connector._features_to_docs()
    logging.info(f"Converted {len(feature_docs)} Features or FeatureGroups to documents")
    res_local = indexes['geojson_osm_indexer']._index(documents=feature_docs)
    return res_local

def generate_combined_feature_collection(doc_list: List[Document]):
    features = []
    for doc in doc_list:
        if "feature" in doc.metadata:
            feature = geojson.Feature(geometry=json.loads(doc.metadata["feature"]), properties=doc.metadata)
            features.append(feature)
        
        elif "features" in doc.metadata:
            feature_collection = geojson.loads(doc.metadata['features'])
            feature_list = list(feature_collection['features'])
            features.extend(feature_list)

    combined_feature_collection  = geojson.FeatureCollection(features)
    # geojson_str = geojson.dumps(combined_feature_collection, sort_keys=True, indent=2)

    return combined_feature_collection

@app.get("/retrieve_geojson")
async def retrieve_geojson(query: str):
    features = indexes['geojson_osm_indexer'].retriever.invoke(query)

    feature_collection = generate_combined_feature_collection(features)

    spatial_extent = calculate_bounding_box(feature_collection)
    properties = summarize_feature_collection_properties(feature_collection)

    summary = f"""Summary of found features:
        {properties}
    	
    Spatial Extent of all features: {spatial_extent}
    """

    return feature_collection, summary


@app.get("/clear_index")
async def clear_index(index_name: str, api_key: APIKey = Depends(get_api_key)):
    if index_name not in indexes and index_name != 'geojson':
        raise HTTPException(status_code=400, detail="Invalid index name")
    
    if index_name == 'geojson':
        logging.info("Clearing geojson index")
        indexes['geojson_osm_indexer']._clear()
    else:
        logging.info(f"Clearing index: {index_name}")
        indexes[index_name]._clear()
    
    return {'message': 'Index cleared'}


@app.get("/retrieve_with_id")
async def retrieve_with_id(index_name: str, _id: str):
    if index_name not in indexes:
        raise HTTPException(status_code=400, detail="Invalid index name")
    retrieved_id = indexes[index_name]._get_doc_by_id(_id)
    return {'id': retrieved_id}

@app.get("/remove_doc_from_index")
async def remove_doc_from_index(index_name: str, _id: str, api_key: APIKey = Depends(get_api_key)):
    if index_name not in indexes:
        raise HTTPException(status_code=400, detail="Invalid index name")
    result = indexes[index_name]._delete_doc_from_index(_id)
    return result

# Edit this to add the chain you want to add
# add_routes(app, call_graph, path="/data")

for index_name, index_instance in indexes.items():
    add_routes(app, index_instance.retriever, path=f"/retrieve_{index_name}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", reload=False, port=8000)
