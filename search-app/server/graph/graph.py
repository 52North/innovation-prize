from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict
from typing import List
from langchain_core.documents import Document
import re
from langchain_core.runnables.graph import CurveStyle, NodeColors, MermaidDrawMethod
from IPython.display import display, HTML, Image
from .actions import (
    off_topic_parser,
    search_criteria_parser,
    check_search_criteria, 
    follow_up_generator, 
    temporal_dimension_parser, 
    spatial_context_parser, 
    search_tool, 
    tavily_search, 
    final_answer_chain
)
import logging 

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

class GraphState(TypedDict):
    off_topic: str
    off_topic_answer: str
    query: str
    temporal_required: str
    follow_up: str
    search_dict: dict
    ready_to_retrieve: str
    documents: List[str]
    final_answer_generated: str


class SpatialRetrieverGraph(StateGraph):
    def __init__(self, state: GraphState):
        super().__init__(state)
        self.setup_graph()

    def setup_graph(self):
        # Define the nodes
        self.add_node("decide_if_data_search", self._decide_if_data_search)
        self.add_node("early_end", self._early_end)
        self.add_node("process_query", self._process_query)
        self.add_node("temporal_parser", self._temporal_parser)
        self.add_node("analyze_search_dict", self._analyze_search_dict)
        self.add_node("follow_up_gen", self._follow_up_gen)
        self.add_node("search", self._search)
        # self.add_node("web_search", self._web_search)
        self.add_node("final_answer", self._final_answer)

        # Build graph
        self.set_entry_point(
            "decide_if_data_search"
        )

        self.add_conditional_edges(
            "decide_if_data_search",
            self._router_init_graph,
            {
                "no_data_retrieval": "early_end",
                "process_query": "process_query",
            },
        )
        self.add_edge("early_end", END)
        
        self.add_edge("process_query", "temporal_parser")
        self.add_edge("temporal_parser", "analyze_search_dict")

        self.add_conditional_edges(
            "analyze_search_dict",
            self._router_follow_up,
            {
                "search": "search",
                # "web_search": "web_search",
                "follow_up_gen": "follow_up_gen",
            },
        )

        # self.add_edge("web_search", "final_answer")
        self.add_edge("search", "final_answer")
        self.add_edge("final_answer", END)
        self.add_edge("follow_up_gen", END)

    def _decide_if_data_search(self, state):
        print("---deciding user input is about data---")
        query = state["query"]

        off_topic_answer = off_topic_parser.invoke({"input": query})

        if off_topic_answer["off_topic"] == "yes":
            return {"off_topic": "yes", "off_topic_answer": off_topic_answer["off_topic_answer"]}
        else:
            return {"off_topic": "no"}
    
    def _early_end(self, state):
        print("---early_end_because_off-topic---")
        final_answer = state["off_topic_answer"]
        return {"final_answer_generated": final_answer}
    
    def _process_query(self, state):
        print("---processing_query---")
        query = state["query"]

        if state["search_dict"] is None:
            search_dict = search_criteria_parser.invoke(query)
        else:  # Fetching search_dict from memory
            search_dict = state["search_dict"]
            updated_search_dict = search_criteria_parser.invoke(query)
            # Overwrite values with new inputs
            for key in updated_search_dict:
                if key in search_dict and search_dict[key] == '':
                    search_dict[key] = updated_search_dict[key]

        return {"query": query, "search_dict": search_dict}
    
    def _temporal_parser(self, state):
        print("---checking if temporal dimension necessary---")

        query = state["query"]

        pattern = re.compile(r'\b(yes|no)\b', re.IGNORECASE)
        parse_temporal = temporal_dimension_parser.invoke({"query": query})
        temporal_flag = pattern.findall(parse_temporal)[0]

        print(f"----temporal dimension required -> {temporal_flag}")

        return {'temporal_required': temporal_flag}


    def _analyze_search_dict(self, state):
        print("---analyze_search_dict---")

        search_dict = state["search_dict"]
        temporal_required = state["temporal_required"]

        grader = check_search_criteria.invoke({"search_dict": search_dict,
                                            "temporal_required": temporal_required})

        if grader["search_dict_complete"] == "yes":
            ready_to_retrieve = "yes"
        else:
            ready_to_retrieve = "no"

        return {"search_dict": search_dict, "ready_to_retrieve": ready_to_retrieve}


    def _follow_up_gen(self, state):
        print("---follow_up_gen---")

        search_dict = state["search_dict"]

        follow_up = follow_up_generator.invoke({"search_dict": search_dict})

        return {"follow_up": follow_up}


    def _search(self, state):
        print("---search---")
        search_dict = state["search_dict"]
        query_string = ' '.join([v for v in search_dict.values()])
        
        documents = state["documents"]

        print(
            f"---starting search in pygeoapi index with following search criteria: \n{query_string}---")
        docs = search_tool.invoke({"query_string": query_string})
        search_results = "\n".join([d.page_content for d in docs])
        search_results = Document(page_content=search_results)
        if documents is not None:
            documents.append(search_results)
        else:
            documents = [search_results]
        return {"documents": docs, "query": query_string}


    def _web_search(self, state):
        # Web search
        search_criteria = state["search_dict"]
        query_string = ' '.join([v for v in search_criteria.values()])

        documents = state["documents"]

        print(
            f"---starting web_search with following search criteria: \n{query_string}---")
        docs = tavily_search.invoke(query_string)
        web_results = "\n".join([d.page_content for d in docs])
        web_results = Document(page_content=web_results)
        if documents is not None:
            documents.append(web_results)
        else:
            documents = [web_results]
        return {"documents": docs, "query": query_string}


    def _final_answer(self, state):
        query = state["query"]
        documents = state["documents"]

        final_answer_generated = final_answer_chain.invoke(
            {"context": documents, "query": query})
        return {"final_answer_generated": final_answer_generated}

    # conditional edge:
    def _router_init_graph(self, state):
        print("---router to decide if follow_up_or_start_retrieval---")
        if state["off_topic"] == "yes":
            print("---route to no_data_retrieval---")
            # return "search"
            return "no_data_retrieval"
        else:
            print("---route to process_query---")
            return "process_query"

    def _router_follow_up(self, state):
        print("---router to decide if follow_up_or_start_retrieval---")
        if state["ready_to_retrieve"] == "yes":
            print("---route to search---")
            return "search"
            # return "web_search"
        else:
            print("---route to follow_up---")
            return "follow_up_gen"
        

