from typing import Annotated, Sequence, TypedDict, List
from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph
import operator
from langchain_core.messages import AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
import json
from datetime import datetime
from .actions import (
    run_converstation_chain,
    final_answer_chain,
    generate_search_tool,
    spatial_context_extraction_tool
    )
from .spatial_utilities import check_within_bbox
import logging
import ast

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)

def is_valid_json(myjson):
    try:
        json_object = json.loads(myjson)
    except ValueError as e:
        return False
    return True

class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    search_criteria: str
    spatio_temporal_context: dict
    search_results: List
    ready_to_retrieve: str
    index_name: str

class SpatialRetrieverGraph(StateGraph):
    def __init__(self, 
                 state: State, 
                 thread_id: int, 
                 memory, 
                 search_indexes: dict,
                 collection_router,
                 conversational_prompts: dict=None
                 ):
        super().__init__(state)
        self.setup_graph()
        self.counter = 0
        self.thread_id = thread_id
        self.memory = memory
        self.search_indexes = search_indexes
        self.conversational_prompts = conversational_prompts
        self.route_layer = collection_router.rl
        self.search_indexes = search_indexes
        self.collection_info_dict = collection_router.coll_dicts
        
        # This takes generates an individual search tool for all collections available 
        self.search_tools = {c['collection_name']: generate_search_tool(c) for c in self.collection_info_dict}
     
    def setup_graph(self):
        self.add_node("conversation", self.run_conversation)
        self.add_node("extract_spatio_temporal_context", self.extract_spatio_temporal_context)
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
        
    async def run_conversation(self, state: State):
        # Restore the state from memory
        history_from_memory = await self._get_history_from_memory()
        if history_from_memory:
            print("---start conversation (with history)")
            chat_history = [message for h in history_from_memory for message in h['messages']]
        else:
            print("---start conversation (no previous messages)")
            chat_history = []
        
        # check if already search_criteria in state. if yes, use semantic router to choose prompt and correct search index
        search_criteria = state.get("search_criteria", "")
        if search_criteria:
            route_choice = self.route_layer(search_criteria)
        else:
            route_choice = self.route_layer(state["messages"][-1].content)

        prompt = None
        if route_choice.name:
            logging.info(f"Chosen route: {route_choice.name}")
            state["index_name"] = route_choice.name
            prompt = self.conversational_prompts[route_choice.name]
        else:
            logging.info("No route chosen, routing to default")
        
        logging.info(f"Custom prompt:{prompt}")
        response, parsed_dict = run_converstation_chain(input=state["messages"][-1].content,
                                                        chat_history=chat_history,
                                                        prompt=prompt)
        
        if response.content and is_valid_json(response.content):
            answer = json.loads(response.content).get("answer", "")
        else:
            answer = "Sorry, I am only designed to help you with finding data. Please try again typing your request :)"

        state["messages"].append(AIMessage(content=answer))
        state["search_criteria"] = parsed_dict.get("search_criteria", "")
        state["ready_to_retrieve"] = parsed_dict.get("ready_to_retrieve", "no")
        return state

    def extract_spatio_temporal_context(self, state: State):
        print("---extracting spatial context of search")
        spatio_temporal_context = state.get('spatio_temporal_context', None)

        if spatio_temporal_context:
            spatial_extent = spatio_temporal_context.get('extent', [])
            temporal_extent = spatio_temporal_context.get('temporal', "")

        if not spatio_temporal_context:
            spatial_context_str = spatial_context_extraction_tool.invoke({"query": str(state['search_criteria'])})
            spatial_extent = ast.literal_eval(spatial_context_str).get("extent", [])

            state['spatio_temporal_context'] = spatial_extent
            
            #Todo: also try to derive temporal extent from inputs
            temporal_extent = ""

        logging.info(f"Extracted following spatial context: {spatial_extent} and following temporal extent: {temporal_extent}")
        return state
    
    def run_search(self, state: State):
        print("---running a search")
        logging.info(f"Search criteria used: {state['search_criteria']}")
        index_name = state.get("index_name", "")

        search_index = self.search_indexes[index_name]
        search_tool = self.search_tools[index_name]

        if index_name:
            logging.info(f"Starting search in index: {index_name} using this tool: {search_tool.name}")
            
            search_results = search_tool.invoke({"query": str(state['search_criteria']),
                                                                        "search_index": search_index,
                                                                        "search_type": "similarity",
                                                                        "k": 10})
        else: 
            tavily_search = TavilySearchResults()  
            search_results = tavily_search.invoke(state["search_criteria"])

        state["search_results"] = search_results

        state["messages"].append(AIMessage(content=f"Search results: {search_results}"))
        return state

    def should_continue(self, state: State) -> str:
        if state.get("ready_to_retrieve") == "yes":
            print("---routing to spatial context extractor, then to search")
            return "extract_spatio_temporal_context"
        else:
            return "human"

    def final_answer(self, state: State) -> str:
        for c in self.collection_info_dict:
            if c['collection_name'] == state['index_name']:
                search_index_info = c.pop('sample_docs', None)
        
        #Todo: use the temporal constraint (e.g. as filter)
        try:
            if state["index_name"] == "geojson":        
                # Check if results match spatial context of query
                query_bbox = state['spatio_temporal_context']
                search_results = check_within_bbox(search_results=state["search_results"],
                                                bbox=query_bbox)
                
                logging.info(f"I found: {len(search_results)} using the query-bbox {query_bbox}")

                doc_contents = "\n\n".join(doc.page_content for doc in search_results)
    
                context = f"""I searched in this search index: {search_index_info}.
                The top-{len(search_results)} search results in the specified spatial extent are: {doc_contents}"""               

            else:
                search_results = state["search_results"][:10]
                doc_contents = "\n\n".join(doc.page_content for doc in search_results)
                context = f"""I searched in this search index: {search_index_info}.
                The top-{len(search_results)} search results are: {doc_contents}"""
            
            if len(search_results) < 1:
                context = "No search results found using the current search criteria" 
                state['search_results'] = []
            query = state["search_criteria"]
            answer = final_answer_chain.invoke({"query": query,
                                                "context": context}).strip()
        except:
            answer = "Sorry I was not able to process your input. Can you please try again?"

        state["messages"].append(AIMessage(content=answer))
        return state
    
    def _get_current_timestamp(self):
        return datetime.now().isoformat() + "+00:00"
    
    async def save_state(self, state: State):
        print(f"---saving state for thread: {self.thread_id}")

        checkpoint = {"ts": self._get_current_timestamp(), "data": state}
        config = {"configurable": {"thread_id": self.thread_id}}         
        await self.memory.aput(config=config, checkpoint=checkpoint)
        
        return state

    async def _get_history_from_memory(self):
        config = {"configurable": {"thread_id": self.thread_id}}
        history = [checkpoint.checkpoint["data"] async for checkpoint in self.memory.alist(config=config)]
        print(f"---retrieving state for thread: {self.thread_id}")
        if history:
            return history
        return None