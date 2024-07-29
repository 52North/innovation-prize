from typing import Annotated, Sequence, TypedDict, List
from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph
import operator
from langchain_core.messages import AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults
import json
from .actions import (
    run_converstation_chain,
    final_answer_chain,
    )


class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    search_criteria: str
    search_results: List
    ready_to_retrieve: str

class SpatialRetrieverGraph(StateGraph):
    def __init__(self, state: State):
        super().__init__(state)
        self.setup_graph()

    def setup_graph(self):
        self.add_node("conversation", self.run_conversation)
        self.add_node("tavily_search", self.run_tavily_search)
        self.add_node("final_answer", self.final_answer)

        self.add_conditional_edges(
            "conversation",
            self.should_continue,
            {
                "human": END,
                "tavily_search": "tavily_search"
            }
        )
        self.add_edge("tavily_search", "final_answer")
        self.add_edge("final_answer", END)

        self.set_entry_point("conversation")

    def run_conversation(self, state: State):
        response, parsed_dict = run_converstation_chain(state["messages"][-1].content)
        answer = json.loads(response.content).get("answer", "")

        state["messages"][-1] = AIMessage(content=answer)
        state["search_criteria"] = parsed_dict.get("search_criteria", "")
        state["ready_to_retrieve"] = parsed_dict.get("ready_to_retrieve", "no")
        return state

    def run_tavily_search(self, state: State):
        print("---running a tavily search")
        tavily_search = TavilySearchResults()
        search_results = tavily_search.invoke(state["search_criteria"])
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
        answer = final_answer_chain.invoke({"query": query, "context": context}).strip()
        state["messages"].append(AIMessage(content=answer))
        return state
