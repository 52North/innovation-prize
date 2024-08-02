from fastapi import FastAPI, HTTPException
import asyncio
from fastapi.responses import RedirectResponse
from langserve import add_routes
from graph.graph import SpatialRetrieverGraph, State
from langchain_core.runnables import chain
from config.config import Config
from indexing.indexer import Indexer
from connectors.pygeoapi_retriever import PyGeoAPI
from connectors.geojson_osm import GeoJSON
from langchain_core.runnables.graph import MermaidDrawMethod
from langchain.schema import Document
from langchain_core.messages import HumanMessage, AIMessage
from fastapi.middleware.cors import CORSMiddleware
from .utils import SessionData, cookie, verifier, backend
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from fastapi import HTTPException, FastAPI, Depends, Response, Security
from fastapi.security.api_key import APIKeyHeader, APIKey
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from uuid import UUID, uuid4
from typing import List, Optional
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
"""
# Generate a visualization of the current dialog-module workflow
graph_visualization = graph.get_graph().draw_mermaid_png(
    draw_method=MermaidDrawMethod.API,
)
with open("./graph/current_workflow.png", "wb") as f:
    f.write(graph_visualization)
"""

# Create a dictionary of indexes
indexes = {
    "pygeoapi": Indexer(index_name="pygeoapi"),
}

# Add indexer for local geojson with OSM features
local_file_indexer = Indexer(index_name="geojson", 
                             score_treshold=0.4, 
                             k = 20,
                             #use_hf_model=True,
                             #embedding_model="ellenhp/osm2vec-bert-v1"
                            )
# Add connection to local file including building features 
# Replace the value for tag_name argument if you have other data 
local_file_connector = GeoJSON(tag_name="building")


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

    graph = SpatialRetrieverGraph(state=State(messages=[], search_criteria="", search_results=[], ready_to_retrieve=""), 
                                  thread_id=session_id, memory=memory).compile()

    data = SessionData(session_id=session_id)

    await backend.create(session, data)
    cookie.attach_to_response(response, session)

    return {"message": f"created session for {session}"}

"""
@chain
async def call_graph(query: str, session_id: UUID = Depends(cookie), session_data: SessionData = Depends(verifier)):
    if graph is not None:
        print(f"-#-#--Running graph---- Using session_id: {str(session_id)}")
        print(f"session_data: {session_data}")
        inputs = {"messages": [HumanMessage(content=query)]}
        graph.graph.thread_id = "test"
        response = await graph.ainvoke(inputs)
    else:
        raise HTTPException(status_code=400, detail="No session created")
    return response
"""
@app.get("/test_api_key")
async def test_api_key(api_key: APIKey = Depends(get_api_key)):
    return f"Entered API KEY: {api_key}"

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

@app.get("/index_local_files")
async def index_local_files(api_key: APIKey = Depends(get_api_key)):
    # await local_file_connector.add_descriptions_to_features()
    feature_docs = await local_file_connector._features_to_docs()
    res_local = local_file_indexer._index(documents=feature_docs)
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
    geojson_str = geojson.dumps(combined_feature_collection, sort_keys=True, indent=2)

    return geojson_str

@app.get("/retrieve_geojson")
async def retrieve_geojson(query: str):
    features = local_file_indexer.retriever.invoke(query)

    return generate_combined_feature_collection(features)


@app.get("/clear_index")
async def clear_index(index_name: str, api_key: APIKey = Depends(get_api_key)):
    if index_name not in (indexes, 'geojson'):
        raise HTTPException(status_code=400, detail="Invalid index name")
    elif index_name == 'geojson':
       local_file_indexer._clear()
    else: 
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
