from .prompts import(
    generate_conversation_prompt,
    generate_final_answer_prompt
)
from langchain_openai import ChatOpenAI
from config.config import Config
from langchain_openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.output_parsers.json import SimpleJsonOutputParser
from langchain_core.output_parsers import StrOutputParser
import json
from langchain.tools import tool
from indexing.indexer import Indexer


config = Config('./config/config.json')

OPENAI_API_KEY = config.openai_api_key
TAVILY_API_KEY = config.tavily_api_key

llm = ChatOpenAI(model="gpt-3.5-turbo-0125",
                 model_kwargs={ "response_format": { "type": "json_object" } })

final_answer_llm = OpenAI(temperature=0)




"""
chain_with_message_history = RunnableWithMessageHistory(
    conversation_chain,
    lambda session_id: memory,
    input_messages_key="input",
    history_messages_key="chat_history",
)

# Example usage
def run_converstation_chain(input: str):
    history =  chain_with_message_history.invoke(
        {"input": input},
        {"configurable": {"session_id": "unused"}},
    )
    parsed_dict = json.loads(history.content)

    return history, parsed_dict
"""
def run_converstation_chain(input: str, chat_history, prompt=None):
    # Chains
    conversation_chain = generate_conversation_prompt(system_prompt=prompt)| llm 

    history =  conversation_chain.invoke(
        {"input": input,
         "chat_history": chat_history}
    )
    parsed_dict = json.loads(history.content)
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
    index = Indexer(index_name=index_name, score_treshold=0.3)
    "Takes a search_dict as input and searches for data"
    docs = index.retriever.invoke(query_string)
    return docs