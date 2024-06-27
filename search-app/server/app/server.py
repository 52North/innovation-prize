from fastapi import FastAPI, HTTPException
import asyncio
from fastapi.responses import RedirectResponse
from langserve import add_routes
from graph.graph import SpatialRetrieverGraph, GraphState
from langchain_core.runnables import chain
from config.config import Config
from indexing.indexer import Indexer
from connectors.pygeoapi_retriever import PyGeoAPI
from langchain_core.runnables.graph import MermaidDrawMethod
import logging

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)

config = Config('./config/config.json')

# Init graph-app
graph = SpatialRetrieverGraph(GraphState).compile()

# Generate a visualization of the current dialog-module workflow
graph_visualization = graph.get_graph().draw_mermaid_png(
    draw_method=MermaidDrawMethod.API,
)
with open("./graph/current_workflow.png", "wb") as f:
    f.write(graph_visualization)

# Create a dictionary of indexes
indexes = {
    "pygeoapi": Indexer(index_name="pygeoapi"),
}


@chain
def call_graph(query: str):
    return graph.invoke(input={"query": query})

app = FastAPI()

@app.get("/")
async def redirect_root_to_docs():
    return RedirectResponse("/docs")

@app.get("/fetch_documents")
async def fetch_documents(indexing: bool=True):
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

@app.get("/clear_index")
async def clear_index(index_name: str):
    if index_name not in indexes:
        raise HTTPException(status_code=400, detail="Invalid index name")
    indexes[index_name]._clear()
    return {'message': 'Index cleared'}

@app.get("/retrieve_with_id")
async def retrieve_with_id(index_name: str, _id: str):
    if index_name not in indexes:
        raise HTTPException(status_code=400, detail="Invalid index name")
    retrieved_id = indexes[index_name]._get_doc_by_id(_id)
    return {'id': retrieved_id}

@app.get("/remove_doc_from_index")
async def remove_doc_from_index(index_name: str, _id: str):
    if index_name not in indexes:
        raise HTTPException(status_code=400, detail="Invalid index name")
    result = indexes[index_name]._delete_doc_from_index(_id)
    return result

# Edit this to add the chain you want to add
add_routes(app, call_graph, path="/data")

for index_name, index_instance in indexes.items():
    add_routes(app, index_instance.retriever, path=f"/retrieve_{index_name}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
