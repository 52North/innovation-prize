from typing import Annotated, Sequence, TypedDict, List
from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph
from langchain.schema import Document
import operator
from langchain_core.messages import AIMessage, HumanMessage
from langchain_community.tools import DuckDuckGoSearchResults
# from langchain_community.tools import TavilySearchResults
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import json
from datetime import datetime
from .actions import (
    run_converstation_chain,
    final_answer_chain,
    generate_search_tool,
    check_if_conversational
)

import asyncio
from contextlib import asynccontextmanager
from .spatial_utilities import check_within_bbox, spatial_context_extraction_tool
from loguru import logger
import ast
from functools import lru_cache
from typing import Type
from uuid import UUID, uuid4



def is_valid_json(myjson):
    try:
        json_object = json.loads(myjson)
    except ValueError as e:
        return False
    return True


def replace_messages(existing, new):
    return new

class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], replace_messages]
    search_criteria: str
    broader_terms: str
    narrower_terms: str
    spatio_temporal_context: dict
    search_results: List
    ready_to_retrieve: str
    index_name: str
    custom_system_prompt: str


class SpatialRetrieverGraph(StateGraph):
    def __init__(
        self,
        state: State,
        thread_id: int,
        memory_path,
        search_indexes: dict,
        collection_router,
        conversational_prompts: dict = None,
        custom_system_prompt: str = None,
    ):
        super().__init__(State)

        self.setup_graph()

        self.counter = 0
        self.thread_id = thread_id
        self.memory_path = memory_path
        self.search_indexes = search_indexes
        self.conversational_prompts = conversational_prompts
        self.route_layer = collection_router.rl
        self.search_indexes = search_indexes
        self.collection_info_dict = collection_router.coll_dicts

        # This takes generates an individual search tool for all collections available
        self.search_tools = {c['collection_name']: generate_search_tool(
            c) for c in self.collection_info_dict}

    def setup_graph(self):
        self.add_node("conversation", self.run_conversation)
        self.add_node("extract_spatio_temporal_context",
                      self.extract_spatio_temporal_context)
        self.add_node("search", self.run_search)
        self.add_node("final_answer", self.final_answer)
        self.add_node("save_state", self.save_state)

        self.add_conditional_edges(
            "conversation",
            self.should_continue,
            {
                "human": "save_state",
                "extract_spatio_temporal_context": "extract_spatio_temporal_context"
            }
        )

        self.add_edge("extract_spatio_temporal_context", "search")
        self.add_edge("search", "final_answer")
        self.add_edge("final_answer", "save_state")
        self.add_edge("save_state", END)

        self.set_entry_point("conversation")

    @asynccontextmanager
    async def session(self):
        # Set up any session-wide resources
        session_data = {}
        try:
            yield session_data
        finally:
            # Clean up session resources
            pass

    @lru_cache(maxsize=128)
    def get_route_choice(self, thread_id: int, input_text: str):
        return self.route_layer(input_text)

    async def run_conversation(self, state: State):
        # Restore the state from memory
        history_from_memory = await self._get_history_from_memory()
        if history_from_memory:
            print("---start conversation (with history)")
            chat_history = [
                message for h in history_from_memory for message in h['messages']]
            
            chat_history.append(HumanMessage(content=state["messages"][-1].content))
            
            logger.info(f"Messages after loading history: {chat_history}")
        else:
            print("---start conversation (no previous messages)")
            chat_history = [HumanMessage(content=state["messages"][-1].content)]

        # Check if user just inputs a conversational message, such as "hello". In this case we take a shortcut.
        if len(chat_history) < 5:
            if check_if_conversational(input_str=state["messages"][-1].content):
                state["messages"].append(AIMessage(
                    content="Hi, I'm here to assist you with finding data. Please let me know what datasets you are looking for"))
                return state

        # check if already search_criteria in state. if yes, use semantic router to choose prompt and correct search index
        search_criteria = state.get("search_criteria", "")
        input_text = search_criteria or ', '.join(
            [m.content for m in state["messages"][-3:]])
        route_choice = self.get_route_choice(self.thread_id, input_text)

        prompt = None

        if 'custom_system_prompt' in state:
            logger.info(f"Using custom system prompt from API call: {state['custom_system_prompt']}")
            prompt = state['custom_system_prompt']
        else:       
            if route_choice.name:
                logger.info(f"Chosen route: {route_choice.name}")
                state["index_name"] = route_choice.name
                prompt = self.conversational_prompts[route_choice.name]
            else:
                logger.info("No route chosen, routing to default")

        response = run_converstation_chain(input=state["messages"][-1].content,
                                           chat_history=chat_history,
                                           prompt=prompt)

   

        chat_history.append(AIMessage(content=response.get("answer")))

        state["messages"].append(AIMessage(content=response.get("answer")))

        logger.info(f"Chat history: {chat_history}")
        logger.info(f"State messages at the end: {state['messages']}")

        state["messages"] = chat_history

        state["search_criteria"] = response.get("search_criteria", "")
        state["ready_to_retrieve"] = response.get(
            "ready_to_retrieve", "no").lower()
        state["narrower_terms"] = response.get("narrower_terms", "")
        state["broader_terms"] = response.get("broader_terms", "")

        return state

    async def extract_spatio_temporal_context(self, state: State):
        print("---extracting spatial context of search")
        spatio_temporal_context = state.get('spatio_temporal_context', None)

        if spatio_temporal_context:
            spatial_extent = spatio_temporal_context.get('extent', [])
            temporal_extent = spatio_temporal_context.get('temporal', "")

        if not spatio_temporal_context:
            spatial_context = await spatial_context_extraction_tool.ainvoke(
                {"query": str(state['search_criteria'])})
            
            logger.info(
                 f"Automatically derived spatial context: {spatial_context}")
            
            spatial_extent = spatial_context.get("extent", [])
            # spatial_context_str = await spatial_context_extraction_tool.ainvoke(
            #     {"query": str(state['search_criteria'])})

            # logger.info(
            #     f"Automatically derived spatial context: {spatial_context_str}")

            # try:
            #     spatial_extent_dict = ast.literal_eval(spatial_context_str)
            #     if spatial_extent_dict:
            #         spatial_extent = spatial_extent_dict.get("extent", [])
            #     else:
            #         spatial_extent = []
            # except (ValueError, SyntaxError) as e:
            #     logger.debug(f"could not extract spatial context: {str(e)}")
            #     spatial_extent = []

            state['spatio_temporal_context'] = spatial_extent

            # Todo: also try to derive temporal extent from inputs
            temporal_extent = ""

        logger.info(
            f"Extracted following spatial context: {spatial_extent} and following temporal extent: {temporal_extent}")
        return state

    async def run_search(self, state: State):
        print("---running a search")
        logger.info(f"Search criteria used: {state['search_criteria']}")
        index_name = state.get("index_name", "")

        if index_name in self.search_indexes:
            search_index = self.search_indexes[index_name]
            search_tool = self.search_tools[index_name]
        
            logger.info(
                f"Starting search in index: {index_name} using this tool: {search_tool.name}")

            search_results = await search_tool.ainvoke({"query": str(state['search_criteria']),
                                                        "search_index": search_index,
                                                        "search_type": "similarity",
                                                        "k": 20})
        else:  # web search
            # tavily_search = TavilySearchResults()
            # search_results = await tavily_search.ainvoke(state["search_criteria"])
            ddgs_search = DuckDuckGoSearchResults()
            search_results = await ddgs_search.ainvoke(state["search_criteria"])

        state["search_results"] = search_results

        return state

    def should_continue(self, state: State) -> str:
        if state.get("ready_to_retrieve") == "yes" and state['search_criteria']:
            print("---routing to spatial context extractor, then to search")
            return "extract_spatio_temporal_context"
        else:
            print("---routing to save state")
            return "human"

    async def final_answer(self, state: State):
        async with self.session() as session:
            search_index_info = next(
                (c for c in self.collection_info_dict if c['collection_name'] == state.get('index_name')), None)
            if search_index_info:
                search_index_info = search_index_info.copy()
                search_index_info.pop('sample_docs', None)
            try:
                search_results = []
                # Todo: do not hard code index name here
                if state.get("index_name", "") == "geojson":
                    query_bbox = state['spatio_temporal_context']

                    all_results = await asyncio.to_thread(
                        check_within_bbox,
                        search_results=state["search_results"],
                        bbox=query_bbox
                    )
            
                    search_results = all_results[:5]
                    logger.info(
                        f"Found: {len(search_results)} using query-bbox {query_bbox}")
                    doc_contents = "\n\n".join(
                        doc.page_content for doc in search_results)
                    context = f"Searched index: {search_index_info}. Top-{len(search_results)} results in spatial extent: {doc_contents}"

                else:
                    if isinstance(state.get('search_results'), list):  
                        search_results = state["search_results"][:10]
                    else:
                        search_results = state["search_results"]

                    logger.info(f"search results: {search_results}")

                    doc_contents = "\n\n".join(
                        doc.page_content if isinstance(doc, Document) else doc.get("snippet", "")
                        for doc in search_results
                        if isinstance(doc, Document) or isinstance(doc, dict)
                    )
                    
                    context = f"Searched index: {search_index_info}. Top-{len(search_results)} results: {doc_contents}"

                if not search_results:
                    context = "No search results found using the current search criteria"
                    state['search_results'] = []

                query = state["search_criteria"]
                custom_system_prompt = state.get("custom_system_prompt", None)

                if custom_system_prompt:
                    query = f"System prompt: {custom_system_prompt}. Query: {query}"

                logger.info(f"Context for rag: {context}")
                answer = await final_answer_chain.ainvoke({"query": query, "context": context})
                answer = answer.strip()

            except Exception as e:
                logger.exception(f"Error in final_answer!")
                answer = "Sorry, I encountered an error processing your request. Please try again."

            state["messages"].append(AIMessage(content=answer))
            return state

    def _get_current_timestamp(self):
        return datetime.now().isoformat() + "+00:00"

    async def save_state(self, state: State):
        print(f"---saving state for thread: {self.thread_id}")

        checkpoint = {"ts": self._get_current_timestamp(), 
                      "data": state,
                      "id":  self.thread_id}
        
        config = {"configurable": {"thread_id": self.thread_id, 
                                   "checkpoint_ns": ""}}
        async with AsyncSqliteSaver.from_conn_string(self.memory_path) as memory:
            await memory.aput(config, checkpoint, {}, {})

        return state

    async def _get_history_from_memory(self):
        config = {"configurable": {"thread_id": self.thread_id}}

        async with AsyncSqliteSaver.from_conn_string(self.memory_path) as memory:
            history = [c.checkpoint.get("data") async for c in memory.alist(config)]

        print(f"---retrieving state for thread: {self.thread_id}")
        if history:
            return history
        return None

