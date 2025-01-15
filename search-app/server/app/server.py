import os
from uuid import  uuid4
from typing import List
import geojson
import json
from typing import Optional, Dict, Any

from loguru import logger
from pydantic import BaseModel

from contextlib import asynccontextmanager
from fastapi import HTTPException, FastAPI, Depends, Request, Response, Security
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader, APIKey
from fastapi.middleware.cors import CORSMiddleware

from langserve import add_routes
from langchain.schema import Document
from langchain_core.messages import HumanMessage, AIMessage
# from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.indexer_manager import indexer_manager
from app.utils import (
    SessionData,
    calculate_bounding_box,
    summarize_feature_collection_properties,
    load_conversational_prompts
)
from graph.routers import CollectionRouter
from graph.graph import SpatialRetrieverGraph, State
from connectors.pygeoapi_retriever import PyGeoAPI
from connectors.geojson_osm import GeoJSON
from result_explainer.search_result_explainer import SimilarityExplainer
from indexing.indexer import Indexer
from config.config import (
    CONFIG,
    resolve_abs_path
)



COOKIE_NAME = "search_app-session"

# Define the origins that should be allowed to make requests to your API
origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://localhost:3000",
]

# Init memory:
memory_path = resolve_abs_path(f"{CONFIG.database_dir}/checkpoint.db")


# Authentificate
API_KEY = CONFIG.sdsa_api_key  # Replace with your actual API key
API_KEY_NAME = "x-api-key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


state_session_to_graph = {}


# Add connection to local file including building features
# Replace the value for tag_name argument if you have other data

geojson_osm_connector = GeoJSON(tag_name="building")

# We can also use a osm/geojson that comes from a web resource
# geojson_osm_connector = GeoJSON(file_dir="https://webais.demo.52north.org/pygeoapi/collections/dresden_buildings/items",
#                                tag_name="building")


# Adding conversational routes. We do this here to avoid time-expensive llm calls during inference:
collection_router = CollectionRouter()

# Check if already custom prompts generated and if yes: check if these match the existing search indexes
conversational_prompts = load_conversational_prompts(
    collection_router=collection_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        indexer_manager.initialize()
        indexes = indexer_manager.get_indexes()
        for index_name, index_instance in indexes.items():
            add_routes(app, index_instance.retriever, path=f"/retrieve_{index_name}")
        
        logger.debug("indexes have been initialized and /retrieve_<index-name> routes were added.")
        app.state.indexes = indexes
        yield
    finally:
        indexer_manager.close()
        if hasattr(app.state, "indexes"):
            del app.state.indexes

root_path = os.getenv("ROOT_PATH", "/")
app = FastAPI(root_path=root_path, lifespan=lifespan)

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
    raise HTTPException(status_code=403, detail=f"Could not validate API Key.")



@app.exception_handler(Exception)
async def unicorn_exception_handler(request: Request, exc: Exception):
    logger.error(exc)
    message = str(exc)
    return JSONResponse(
        status_code=500,
        content={"message": f"Oops! {message}"},
    )


@app.get("/")
async def redirect_root_to_docs():
    return RedirectResponse("docs")


async def _create_session(request: Request, response: Response):
    session_id = str(uuid4())

    graph = SpatialRetrieverGraph(state=State(messages=[], 
                                              search_criteria="", 
                                              broader_terms="",
                                              narrower_terms="",
                                              spatio_temporal_context={},
                                              search_results=[], 
                                              ready_to_retrieve=""), 
                                              thread_id=session_id, 
                                              memory_path=memory_path,
                                              search_indexes=request.app.state.indexes,
                                              collection_router=collection_router,
                                              conversational_prompts=conversational_prompts,
                                              custom_system_prompt="",
                                              ).compile()

    data = SessionData(session_id=session_id, graph=graph)

    global state_session_to_graph
    state_session_to_graph.update({session_id: data})
    response.set_cookie(key=COOKIE_NAME, value=session_id, samesite=None, secure=True)
    return session_id

@app.post("/create_session")
async def create_session(request: Request, response: Response):
    session = await _create_session(request, response)
    return {"message": f"new created session: {session}"}


class Query(BaseModel):
    query: str
    spatio_temporal_context: Optional[Dict[str, Any]] = None
    custom_system_prompt: str = None

async def table_exists(cursor, table_name):
    await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    result = await cursor.fetchone()
    return result is not None

@app.post("/data")
async def call_graph(request: Request, response: Response, query_data: Query):
    global state_session_to_graph
    if COOKIE_NAME not in request.cookies:
        session = await _create_session(request, response)
        logger.debug(f"new session created: {session}")
    else:
        session = request.cookies[COOKIE_NAME]
        if session not in state_session_to_graph:
            session = await _create_session(request, response)
            logger.debug(f"session exposed .. new session created: {session}")

    thread_id = session
    session_data = state_session_to_graph[thread_id]
    if not session_data or session_data.graph is None:
        raise HTTPException(status_code=500, detail=f"No data found for session {session}!")
    
    # Add an explicit reset command
    if query_data.query == 'reset':
        async with AsyncSqliteSaver.from_conn_string(memory_path) as memory:
            
            cursor = await memory.conn.cursor()
            if await table_exists(cursor, "checkpoints"):
                await cursor.execute(f"SELECT * FROM checkpoints WHERE thread_id = '{thread_id}';")
                checkpoint = await cursor.fetchone()
                if checkpoint:
                    del state_session_to_graph[session]
                    await cursor.execute(f"DELETE FROM checkpoints WHERE thread_id = '{thread_id}' ;")
                    return {"messages": [AIMessage(content="Okay, let's start a new search. What kind of data are you looking for?")]}

                else:
                    return {"messages": ["No previous chat history"]}
            else:
                return {"messages": ["No previous chat history"]}

    print(f"-#-#--Running graph---- Using session_id: {thread_id}")
    inputs = {"messages": [HumanMessage(content=query_data.query)]}

    if query_data.spatio_temporal_context:
        inputs['spatio_temporal_context'] = query_data.spatio_temporal_context

    if query_data.custom_system_prompt:
        inputs['custom_system_prompt'] = query_data.custom_system_prompt

    graph = session_data.graph
    graph.thread_id = thread_id
    response = await graph.ainvoke(inputs)
    
    return response

@app.get("/fetch_documents")
async def fetch_documents(request: Request, indexing: bool = True, api_key: APIKey = Depends(get_api_key)):
    docs_to_index = []

    # Scrape from pygeoapi resources
    pygeoapi = PyGeoAPI()
    pygeoapi_docs = await pygeoapi.get_docs_for_all_instances()
    logger.info(f"Retrieved {len(pygeoapi_docs)} documents from pygeoapi")

    if indexing:
        # Indexing received docs
        logger.info("Indexing fetched documents in pygeoapi index")
        res_pygeoapi = request.app.state.indexes["pygeoapi"]._index(documents=pygeoapi_docs)

        # In case the collection changes significantly, also update the custom prompts
        if (res_pygeoapi["num_added"] > 20) or (res_pygeoapi["num_updated"] > 20):
            collection_router.setup()
            global conversational_prompts
            conversational_prompts = load_conversational_prompts(collection_router=collection_router)

    return {
        'indexing_results': {
            'pygeoapi': res_pygeoapi,
        }
    }


@app.get("/index_geojson_osm_features")
async def index_geojson_osm(request: Request, api_key: APIKey = Depends(get_api_key)):
    # await local_file_connector.add_descriptions_to_features()
    feature_docs = await geojson_osm_connector._features_to_docs()
    logger.info(f"Converted {len(feature_docs)} Features or FeatureGroups to documents")
    res_local = request.app.state.indexes['geojson']._index(documents=feature_docs)

    if (res_local["num_added"] > 20) or (res_local["num_updated"] > 20):
        collection_router.setup()
        global conversational_prompts
        conversational_prompts = load_conversational_prompts(collection_router=collection_router)

    return res_local


def generate_combined_feature_collection(doc_list: List[Document]):
    features = []
    for doc in doc_list:
        if "feature" in doc.metadata:
            feature = geojson.Feature(geometry=json.loads(
                doc.metadata["feature"]), properties=doc.metadata)
            features.append(feature)

        elif "features" in doc.metadata:
            feature_collection = geojson.loads(doc.metadata['features'])
            feature_list = list(feature_collection['features'])
            features.extend(feature_list)

    combined_feature_collection = geojson.FeatureCollection(features)
    # geojson_str = geojson.dumps(combined_feature_collection, sort_keys=True, indent=2)

    return combined_feature_collection


@app.get("/retrieve_geojson")
async def retrieve_geojson(request: Request, query: str):
    features = request.app.state.indexes['geojson'].retriever.invoke(query)

    feature_collection = generate_combined_feature_collection(features)

    spatial_extent = calculate_bounding_box(feature_collection)
    properties = summarize_feature_collection_properties(feature_collection)

    summary = f"""Summary of found features:
        {properties}

    Spatial Extent of all features: {spatial_extent}
    """

    global conversational_prompts
    conversational_prompts = load_conversational_prompts(collection_router=collection_router)
    return feature_collection, summary


@app.get("/clear_index")
async def clear_index(request: Request, index_name: str, api_key: APIKey = Depends(get_api_key)):
    indexes = request.app.state.indexes
    if index_name not in indexes and index_name != 'geojson':
        raise HTTPException(status_code=400, detail="Invalid index name")

    if index_name == 'geojson':
        logger.info("Clearing geojson index")
        indexes['geojson']._clear()
    else:
        logger.info(f"Clearing index: {index_name}")
        indexes[index_name]._clear()

    return {'message': 'Index cleared'}


@app.get("/retrieve_with_id")
async def retrieve_with_id(request: Request, index_name: str, _id: str):
    indexes = request.app.state.indexes
    if index_name not in indexes:
        raise HTTPException(status_code=400, detail="Invalid index name")
    retrieved_id = indexes[index_name]._get_doc_by_id(_id)
    return {'id': retrieved_id}


@app.get("/remove_doc_from_index")
async def remove_doc_from_index(request: Request, index_name: str, _id: str, api_key: APIKey = Depends(get_api_key)):
    indexes = request.app.state.indexes
    if index_name not in indexes:
        raise HTTPException(status_code=400, detail="Invalid index name")
    result = indexes[index_name]._delete_doc_from_index(_id)
    return result


class ExplainerContext(BaseModel):
    index_name: str
    query: str
    documents: List[Document]


@app.post("/explain_results")
async def explain_results(request: Request, context: ExplainerContext):
    indexes = request.app.state.indexes
    explainer = SimilarityExplainer(search_index=indexes[context.index_name])
    for result in context.documents:
        importance_scores = explainer.explain_similarity(
            context.query, result.page_content)
        result.metadata['relevant_words'] = importance_scores

    return context.documents

# Edit this to add the chain you want to add
#add_routes(app, call_graph, path="/data")

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(app, host="0.0.0.0", reload=False, port=8000)
