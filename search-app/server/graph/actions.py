from langchain_openai import OpenAI
from langchain.tools import tool
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.prompts import PromptTemplate
from langchain_community.retrievers import TavilySearchAPIRetriever
from indexing.indexer import Indexer
import os 
from .prompts import(
    generate_off_topic_answer,
    generate_search_criteria_prompt,
    generate_follow_up_prompt,
    generate_temporal_dim_prompt,
    generate_spatial_prompt,
    generate_final_answer_prompt
)
from config.config import Config

config = Config('./config/config.json')

OPENAI_API_KEY = config.openai_api_key
TAVILY_API_KEY = config.tavily_api_key
#Initialize a LLM
llm = OpenAI(temperature=0)

# Initialize search indexes
indexes = {
    "pygeoapi": Indexer(index_name="pygeoapi", k=3),
    "storymaps": Indexer(index_name="storymaps"),
    "gemet": Indexer(index_name="gemet", score_treshold=0.3),
    "gcmd": Indexer(index_name="gcmd", score_treshold=0.3),
}

###### DECIDE IF USER INTENDS TALKING ABOUT DATA
# follow_up generator
off_topic_prompt, off_topic_parser = generate_off_topic_answer()
off_topic_parser = (
    off_topic_prompt
    | llm
    |off_topic_parser
)

###### GET SEARCH CRITERIA
search_criteria_prompt, search_criteria_parser = generate_search_criteria_prompt()
search_criteria_parser = (
  search_criteria_prompt
  | llm
  | search_criteria_parser
)

# Tool to check if search criteria is complete:
@tool("check_search_criteria")
def check_search_criteria(search_dict: dict,
                          temporal_required: str)->dict:
    """Use this tool to extract spatial, thematic and temporal aspects if users ask for data.
    This tool outputs a search_dict and checks if the search dict is complete"""

    if temporal_required == "no":
      search_dict.pop('temporal', None)

    search_dict_is_complete = all(value not in ["", None] for value in search_dict.values())

    if search_dict_is_complete:
        return {"search_dict_complete": "yes"}
    else:
        return {"search_dict_complete": "no"}

###### GENERATE FOLLOW-UP
# follow_up generator
follow_up_generator = (
    generate_follow_up_prompt()
    | llm
    | StrOutputParser()
)

###### ASSESS TEMPORAL DIMENSION
# Find out if layer has temporal dimension:
# use few-shot learning here
temporal_dimension_parser = (
    generate_temporal_dim_prompt()
    | llm
    | StrOutputParser()
)

###### ASSESS SPATIAL SCALE / RESOLUTION
### Analyze the spatial context in the query:
# Set up a parser + inject instructions into the prompt template.
spatial_context_parser = (
    generate_spatial_prompt()
    | llm
    | StrOutputParser()
)


###### RETRIEVAL 
## Search tool (dummy here. to be replaced)
@tool("search_tool")
def search_tool(
    query_string: str):
    "Takes a search_dict as input and searches for data"
    docs = indexes['pygeoapi'].retriever.invoke(query_string)
    return docs

### try tavily search
tavily_search = TavilySearchAPIRetriever(k=3)


###### FINAL ANSWER 
### Generate final answer
# Post-processing
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# Chain
final_answer_chain = (
    generate_final_answer_prompt()
    | llm 
    | StrOutputParser()
)