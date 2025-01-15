from .prompts import(
    generate_conversation_prompt,
    generate_final_answer_prompt
)

from .spatial_utilities import (
    generate_spatial_context_chain
)
from langchain_openai import OpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers import JsonOutputParser
from langchain.output_parsers import OutputFixingParser
import json
import ast
from langchain.tools import tool
from pydantic import BaseModel, Field
from typing import Literal
import requests
from loguru import logger
from semantic_router import Route
from semantic_router.encoders import OpenAIEncoder
from semantic_router.layer import RouteLayer
from langchain_groq import ChatGroq
from app.llm_manager import LLMManager

llm = LLMManager.get_llm()

from config.config import CONFIG


# llm = ChatGroq(
#     model="llama3-70b-8192",
#     temperature=0,
#     max_tokens=None,
#     timeout=None,
#     max_retries=2,
#     # other params...
# )

# llm = ChatOpenAI(model="gpt-3.5-turbo-0125")

# llm_with_structured_output = ChatOpenAI(model="gpt-3.5-turbo-0125",
#                  model_kwargs={ "response_format": { "type": "json_object" } })

# llm_unstructured = OpenAI(temperature=0, openai_api_key=CONFIG.openai_api_key)
# final_answer_llm = OpenAI(temperature=0, openai_api_key=CONFIG.openai_api_key)

def is_valid_json(myjson):
    try:
        json_object = json.loads(myjson)
    except ValueError:
        return False
    return True


# check if conversational:
routes = [Route(
    name="chitchat",
    utterances=[
        "hello",
        "hi",
        "how's the weather today?",
        "how are things going?",
        "lovely weather today",
        "the weather is horrendous",
        "let's go to the chippy",
    ],
)]
encoder = OpenAIEncoder()

def check_if_conversational(input_str: str) -> bool:
    rl = RouteLayer(encoder=encoder, routes=routes)
    route_choice = rl(input_str)
    if route_choice.name == 'chitchat':
        return True
    else:
        return False

# Define the conversation output data structure.
class ResponseSchema(BaseModel):
    answer: str = Field(description="Your response to the user. Seek for something useful in the input you recieve")
    search_criteria: str = Field(description="List of extracted search criteria.")
    ready_to_retrieve: str = Field(description="'yes' if ready to search, 'no' if more information is needed")
    narrower_terms: str = Field(description="List of more specific search terms.")
    broader_terms: str = Field(description="List of more general search terms.")

def run_converstation_chain(input: str, chat_history, prompt=None):
    output_parser = JsonOutputParser(pydantic_object=ResponseSchema)
    output_fixer = OutputFixingParser.from_llm(parser=output_parser, llm=llm)

    format_instructions = output_parser.get_format_instructions()
    format_instructions += ". WICHTIG: Gebe nur das reine JSON zurück, ohne zusätzlichen Text oder Erklärungen."

    dynamic_prompt = generate_conversation_prompt(format_instructions=format_instructions, system_prompt=prompt)

    # Chains
    conversation_chain = (        
        dynamic_prompt
        | llm
        #| output_parser
    ) 

    logger.info(f"input to converation chain: {input}")

    history =  conversation_chain.invoke(
        {"input": input,
         "chat_history": chat_history}
    )
    parsed_output = output_fixer.parse(history.content)
    return parsed_output


final_answer_chain = (
    generate_final_answer_prompt() | llm | StrOutputParser()
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
        """ """

        search_kwargs={"score_threshold": score_treshold,
                       "k": k}
        
        if search_type == "similarity":
            retriever = search_index.vectorstore.as_retriever(search_kwargs={"k": k})
        else:
            retriever = search_index.vectorstore.as_retriever(search_type=search_type,
                                                              search_kwargs=search_kwargs)

        docs = retriever.invoke(query)
        if search_index.index_name == "pygeoapi":
            for d in docs:
                d.metadata["extent"] = ast.literal_eval(d.metadata["extent"])

        return docs

    search_tool.__doc__ = docstring
    search_tool.func.__name__ = f"search_{collection_name}"

    return search_tool


### spatial context extraction
@tool("spatial_context_extraction_tool")
def spatial_context_extraction_tool(query: str):
    """This tool extracts the spatial entities, scale and extent of a query"""
    # chain = generate_spatial_context_chain(llm=llm_unstructured)
    chain = generate_spatial_context_chain(llm=llm)

    return chain.invoke({"query": query})

