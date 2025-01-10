from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from langserve import add_routes
from graph.graph import SpatialRetrieverGraph, State
from graph.routers import CollectionRouter
from config.config import Config
from indexing.indexer import Indexer
from connectors.pygeoapi_retriever import PyGeoAPI
from connectors.geojson_osm import GeoJSON
from result_explainer.search_result_explainer import SimilarityExplainer
from langchain.schema import Document
from langchain_core.messages import HumanMessage, AIMessage

from fastapi.middleware.cors import CORSMiddleware
from app.utils import (
    SessionData,
    calculate_bounding_box,
    summarize_feature_collection_properties,
    load_conversational_prompts
)

# from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver



from fastapi import HTTPException, FastAPI, Depends, Request, Response, Security
from fastapi.security.api_key import APIKeyHeader, APIKey
# from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
from uuid import UUID, uuid4
from typing import List
import geojson
from pydantic import BaseModel
import json
from loguru import logger
from typing import Optional, Dict, Any

from config.config import CONFIG


COOKIE_NAME = "search_app-session"

# Define the origins that should be allowed to make requests to your API
origins = [
    "http://localhost",
    "http://localhost:5173",
]

# Init memory:
memory_path = "checkpoint.db"
memory = AsyncSqliteSaver.from_conn_string(memory_path)


# Authentificate
API_KEY = CONFIG.sdsa_api_key  # Replace with your actual API key
API_KEY_NAME = "X-API-Key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


state_session_to_graph = {}


# Create a dictionary of indexes
indexes = {
    "pygeoapi": Indexer(index_name="pygeoapi",
                        score_treshold=0.4,
                        k=20),
    "geojson": Indexer(index_name="geojson",  # Add indexer for local geojson with OSM features
                       score_treshold=0.4,
                       k=20,
                       # use_hf_model=True,
                       # embedding_model="Alibaba-NLP/gte-large-en-v1.5"
                       )
}

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
    return RedirectResponse("/docs")


async def _create_session(response: Response):
    session_id = str(uuid4())

    graph = SpatialRetrieverGraph(state=State(messages=[], 
                                              search_criteria="", 
                                              broader_terms="",
                                              narrower_terms="",
                                              spatio_temporal_context={},
                                              search_results=[], 
                                              ready_to_retrieve=""), 
                                              thread_id=session_id, 
                                              memory=memory,
                                              search_indexes=indexes,
                                              collection_router=collection_router,
                                              conversational_prompts=conversational_prompts
                                              ).compile()

    data = SessionData(session_id=session_id, graph=graph)

    global state_session_to_graph
    state_session_to_graph.update({session_id: data})
    response.set_cookie(key=COOKIE_NAME, value=session_id)
    return session_id

@app.post("/create_session")
async def create_session(response: Response):
    session = await _create_session(response)
    return {"message": f"new created session: {session}"}


class Query(BaseModel):
    query: str
    spatio_temporal_context: Optional[Dict[str, Any]] = None


@app.post("/data")
async def call_graph(request: Request, response: Response, query_data: Query):
    global state_session_to_graph
    if COOKIE_NAME not in request.cookies:
        session = _create_session(response=response)
        logger.debug(f"new session created: {session}")
    else:
        session = request.cookies[COOKIE_NAME]
        if session not in state_session_to_graph:
            raise HTTPException(status_code=400, detail="Invalid session!")

    thread_id = session
    session_data = state_session_to_graph[thread_id]
    if not session_data or session_data.graph is None:
        raise HTTPException(status_code=500, detail=f"No data found for session {session}!")
    
    # Add an explicit reset command
    if query_data.query == 'reset':
        #if graph.memory.conn.is_alive():
        if memory.conn.is_alive():
            #async with graph.memory.conn.cursor() as cur:
            async with memory.conn.cursor() as cur:
                # Check if checkpoints exist
                await cur.execute(f"SELECT * FROM checkpoints WHERE thread_id = '{thread_id}';")
                checkpoints = await cur.fetchall()
                if checkpoints:
                    await cur.execute(f"DELETE FROM checkpoints WHERE thread_id = '{thread_id}' ;")
                    return {"messages": [AIMessage(content="Okay, let's start a new search. What kind of data are you looking for?")]}

                else:
                    return {"messages": "No previous chat history"}
        else:
            return {"messages": "No previous chat history"}

    print(f"-#-#--Running graph---- Using session_id: {thread_id}")
    inputs = {"messages": [HumanMessage(content=query_data.query)]}

    if query_data.spatio_temporal_context:
        inputs['spatio_temporal_context'] = query_data.spatio_temporal_context

    graph = session_data.graph
    graph.thread_id = thread_id
    response = await graph.ainvoke(inputs)
    
    return response


@app.get("/fetch_documents")
async def fetch_documents(indexing: bool = True, api_key: APIKey = Depends(get_api_key)):
    docs_to_index = []

    # Scrape from pygeoapi resources
    pygeoapi = PyGeoAPI()
    pygeoapi_docs = await pygeoapi.get_docs_for_all_instances()
    logger.info(f"Retrieved {len(pygeoapi_docs)} documents from pygeoapi")

    if indexing:
        # Indexing received docs
        logger.info("Indexing fetched documents in pygeoapi index")
        res_pygeoapi = indexes["pygeoapi"]._index(documents=pygeoapi_docs)

        # In case the collection changes significantly, also update the custom prompts
        if (res_pygeoapi["num_added"] > 20) or (res_pygeoapi["updated"] > 20):
            collection_router.setup()
            load_conversational_prompts(collection_router=collection_router)

    return {'indexing_results': {
        'pygeoapi': res_pygeoapi,
    }
    }


@app.get("/index_geojson_osm_features")
async def index_geojson_osm(api_key: APIKey = Depends(get_api_key)):
    # await local_file_connector.add_descriptions_to_features()
    feature_docs = await geojson_osm_connector._features_to_docs()
    logger.info(f"Converted {len(feature_docs)} Features or FeatureGroups to documents")
    res_local = indexes['geojson']._index(documents=feature_docs)

    if (res_local["num_added"] > 20) or (res_local["num_updated"] > 20):
        collection_router.setup()
        load_conversational_prompts(collection_router=collection_router)

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
async def retrieve_geojson(query: str):
    features = indexes['geojson'].retriever.invoke(query)

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
        logger.info("Clearing geojson index")
        indexes['geojson']._clear()
    else:
        logger.info(f"Clearing index: {index_name}")
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


class ExplainerContext(BaseModel):
    index_name: str
    query: str
    documents: List[Document]


@app.post("/explain_results")
async def explain_results(context: ExplainerContext):
    # Try to explain results
    explainer = SimilarityExplainer(search_index=indexes[context.index_name])
    for result in context.documents:
        importance_scores = explainer.explain_similarity(
            context.query, result.page_content)
        result.metadata['relevant_words'] = importance_scores

    return context.documents

# Edit this to add the chain you want to add
#add_routes(app, call_graph, path="/data")

for index_name, index_instance in indexes.items():
    add_routes(app, index_instance.retriever, path=f"/retrieve_{index_name}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", reload=False, port=8000)
