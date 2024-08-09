from typing import Annotated, Sequence, TypedDict, List
from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph
import operator
from langchain_core.messages import AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.checkpoint.aiosqlite import AsyncSqliteSaver
import json
from datetime import datetime
from .routers import CollectionRouter
from .actions import (
    run_converstation_chain,
    final_answer_chain,
    search_tool
    )
import logging
import requests

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    search_criteria: str
    search_results: List
    ready_to_retrieve: str
    index_name: str

class SpatialRetrieverGraph(StateGraph):
    def __init__(self, 
                 state: State, 
                 thread_id: int, 
                 memory, 
                 conversational_prompts: dict=None,
                 route_layer=None):
        super().__init__(state)
        self.setup_graph()
        self.counter = 0
        self.thread_id = thread_id
        self.memory = memory
        self.conversational_prompts = conversational_prompts
        self.route_layer = route_layer

    def setup_graph(self):
        self.add_node("conversation", self.run_conversation)
        self.add_node("tavily_search", self.run_tavily_search)
        self.add_node("final_answer", self.final_answer)
        self.add_node("save_state", self.save_state)

        self.add_conditional_edges(
            "conversation",
            self.should_continue,
            {
                "human": "save_state",
                "tavily_search": "tavily_search"
            }
        )
        self.add_edge("tavily_search", "final_answer")
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
        
        response, parsed_dict = run_converstation_chain(input=state["messages"][-1].content,
                                                        chat_history=chat_history,
                                                        prompt=prompt)
        answer = json.loads(response.content).get("answer", "")

        state["messages"].append(AIMessage(content=answer))
        state["search_criteria"] = parsed_dict.get("search_criteria", "")
        state["ready_to_retrieve"] = parsed_dict.get("ready_to_retrieve", "no")
        return state

    def run_tavily_search(self, state: State):
        print("---running a tavily search")
        # tavily_search = TavilySearchResults()       
        # search_results = tavily_search.invoke(state["search_criteria"])
        logging.info(f"Search criteria used: {state['search_criteria']}")
        index_name = state.get("index_name", "")

        #Todo: To enable custom index-based search, wee need to take care that we also use the correct embedding model for encoding queries... 
        """
        if index_name:
            logging.info(f"Starting search in index: {index_name}")
            search_results = search_tool.invoke({"query_string": state['search_criteria'],
                                                 "index_name": index_name})
        else: 
            tavily_search = TavilySearchResults()  
            search_results = tavily_search.invoke(state["search_criteria"])

        """
        tavily_search = TavilySearchResults()  
        search_results = tavily_search.invoke(str(state["search_criteria"]))

        state["search_results"] = search_results

        state["messages"].append(AIMessage(content=f"Search results: {search_results}"))
        return state

    def should_continue(self, state: State) -> str:
        if state.get("ready_to_retrieve") == "yes":
            print("---routing to search")
            return "tavily_search"
        else:
            return "human"

    def final_answer(self, state: State) -> str:
        query, context = state["search_criteria"], state["search_results"]
        answer = final_answer_chain.invoke({"query": query,
                                            "context": context}).strip()
        
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