from .prompts import(
    generate_conversation_prompt,
    generate_final_answer_prompt
)

from .spatial_utilities import (
    generate_spatial_context_chain
)
from langchain_openai import ChatOpenAI
from config.config import Config
from langchain_openai import OpenAI
from langchain_core.output_parsers import StrOutputParser
import json
from langchain.tools import tool
from typing import Literal
import requests
import logging

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


config = Config('./config/config.json')

OPENAI_API_KEY = config.openai_api_key
TAVILY_API_KEY = config.tavily_api_key

llm_with_structured_output = ChatOpenAI(model="gpt-3.5-turbo-0125",
                 model_kwargs={ "response_format": { "type": "json_object" } })

llm_unstructured, final_answer_llm = OpenAI(temperature=0),  OpenAI(temperature=0)


def is_valid_json(myjson):
    try:
        json_object = json.loads(myjson)
    except ValueError as e:
        return False
    return True

def run_converstation_chain(input: str, chat_history, prompt=None):
    # Chains
    conversation_chain = generate_conversation_prompt(system_prompt=prompt)| llm_with_structured_output 

    logging.info(f"input to converation chain: {input}")

    history =  conversation_chain.invoke(
        {"input": input,
         "chat_history": chat_history}
    )
    if history.content and is_valid_json(history.content):
        parsed_dict = json.loads(history.content)
    else: parsed_dict = {}

    return history, parsed_dict

final_answer_chain = (
    generate_final_answer_prompt() | final_answer_llm | StrOutputParser()
)


###### RETRIEVAL 
## Search tool (dummy here. to be replaced)
@tool("search_tool")
def search_tool(
    query_string: str,
    index_name: str):
    "Takes a query_string and a index_name as input and searches for data"
    if index_name == "geojson": 
        response = requests.get(f"http://localhost:8000/retrieve_geojson?query={query_string}")        

    else:
        url = f"http://localhost:8000/retrieve_{index_name}/invoke"
        json = {"input": query_string}
        response = requests.post(url=url, json=json)
    "Takes a search_dict as input and searches for data"
    if response.status_code == 200:
        docs = response.json()
    return docs


### Custom search tools factory
def generate_search_tool(coll_dict):
    collection_name = coll_dict['collection_name']
    collection_description = coll_dict.get('description', '')

    if collection_description:
        docstring = f"Finds information in following collection: {collection_description}"
    else:
        docstring = f"Finds information in following collection: {collection_name}"


    @tool(f"search_{collection_name}")
    def search_tool(query: str, 
                    search_index,
                    search_type: Literal["similarity",
                                         "mmr",
                                         "similarity_score_threshold"]="similarity",
                    score_treshold: float=0.5,
                    k: int=20):
        """"""

        search_kwargs={"score_threshold": score_treshold,
                       "k": k}
        
        if search_type == "similarity":
            retriever = search_index.vectorstore.as_retriever(search_kwargs={"k": k})
        else:
            retriever = search_index.vectorstore.as_retriever(search_type=search_type,
                                                              search_kwargs=search_kwargs)

        docs = retriever.invoke(query)
        
        return docs

    search_tool.__doc__ = docstring
    search_tool.func.__name__ = f"search_{collection_name}"

    return search_tool


### spatial context extraction
@tool("spatial_context_extraction_tool")
def spatial_context_extraction_tool(query: str):
    """This tool extracts the spatial entities, scale and extent of a query"""
    chain = generate_spatial_context_chain(llm=llm_unstructured)

    return chain.invoke({"query": query})