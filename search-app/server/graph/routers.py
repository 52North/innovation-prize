import os
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain.prompts import PromptTemplate
from config.config import Config
import chromadb
from chromadb.config import Settings
import re
from semantic_router import Route
from semantic_router.layer import RouteLayer
from semantic_router.encoders import OpenAIEncoder
from loguru import logger
from app.llm_manager import LLMManager

from config.config import CONFIG


class CollectionRouter():
    def __init__(self):
        self.database_dir = CONFIG.database_dir
        
        self.llm = LLMManager.get_llm()
        # self.llm = ChatOpenAI(model="gpt-4o-mini")
        self.encoder = OpenAIEncoder()
        self.setup()

    def setup(self):
        self.coll_dicts = self.get_collection_info(database_dir=self.database_dir)
        self.routes = [self.generate_route(collection_dict=coll) for coll in self.coll_dicts]
        self.rl = RouteLayer(encoder=self.encoder, routes=self.routes)

    def get_collection_info(self, database_dir: str) -> dict:
        """
        Fetching information about existing collections
        """
        settings = Settings(
            is_persistent=True,
            persist_directory=database_dir,
        )
        client = chromadb.Client(settings=settings)

        collections = client.list_collections()

        coll_dicts = []
        for c in collections:
                logger.info(f"Looking into collection {c.name}")
                if c.name != "langchain":
                    coll = client.get_collection(c.name)
                    number_docs = coll.count()
                    if number_docs == 0:
                        logger.info(f"Collection {c.name} has no indexed records")
                        continue                    
                    top_10_docs = coll.peek()
                    sample_docs = top_10_docs["documents"]
                    unique_keys = {key for d in top_10_docs['metadatas'] for key in d.keys()}
                    coll_dicts.append({
                        "collection_name": c.name,
                        "sample_docs": sample_docs,
                        "metadata_keys": unique_keys if unique_keys else [],
                        "number_docs": number_docs
                        })
        return coll_dicts
    
    def generate_route(self, collection_dict: dict):
        prompt_collection_desc = PromptTemplate(
            template="""You receive a collection from a vector database. 
            Based on the collection's name and a few sample documents, you get an idea of the collection's contents, including its theme, type of data, and any notable characteristics. 
            Now, create a numbered list of example queries that users might submit to the 
            vector store to retrieve relevant information from this collection (ignore location references and proper names that can occur in the samples and generate generic queries)."
            Additionally, generate a brief description (60 words maximum) of the collection's contents, including its theme, type of data, and any notable characteristics
            
            Collection:{collection}""",
            input_variables= ["collection"],
        )

        coll_chain = (
            prompt_collection_desc
            | self.llm
            | StrOutputParser()
        )

        
        result = coll_chain.invoke({"collection": collection_dict})

        # Split the input text into the list and description
        parts = result.split('\n\nDescription:')

        # Handle the numbered list
        list_text = parts[0]
        utterances = re.sub(r'\d+\.\s', '', list_text).split('\n')

        # Handle the description
        description = parts[1] if len(parts) > 1 else ""
        
        # Write the collection description into the coll_dict
        for c in self.coll_dicts:
            if c["collection_name"] == collection_dict["collection_name"]:
                c["description"] = description

        route  = Route(
            name=collection_dict['collection_name'],
            description=description,
            score_threshold=0.7,
            utterances=[u for u in utterances if u],
        )
        return route
        
    def generate_conversation_prompts(self):
        if not self.coll_dicts:
            return {}
        prompt = PromptTemplate(
            template="""You receive a collection from a vector database. Based on the collection name and sample docs, write a prompt for an agent to assist users in finding data. 
            Ignore spatial references and generate a generic prompt (with utf-8 characters only) using this structure:
            **AI Instructions:**
            You are an AI designed to assist users in finding environmental or geospatial datasets. Follow these guidelines:

            1. **Extract Search Criteria:** Identify key information from user queries.
            2. **Refine the Search:** If unavoidable, ask follow-up questions to clarify the search criteria (max 2 times).
            3. **Contextual Responses:** Use the conversation's context to refine the search criteria.
            4. **Determine Readiness:**
            - Set `"ready_to_retrieve": "yes"` when sufficient information is gathered to conduct a search or if the user directly requests a search or indicates readiness.
            - Avoid asking for further clarification if the user's request is already clear and actionable - still generate an answer to the user's
            5. **Generate Search Query:** Once ready, combine all specified criteria to formulate a comprehensive search query. 
            6. **Expand Search Terms:** Suggest narrower or broader search terms if it might improve search results.

            **Response Strategy:**
            - **Be concise:** Deliver clear, straightforward responses without unnecessary elaboration.
            - **Be proactive:** Move to action quickly when enough information is available.
            - **Stay relevant:** Keep follow-up questions focused and avoid general or vague inquiries.
            - **Use affirmations sparingly:** Acknowledge understanding without overuse of affirmations or repeating the user's input.

            **Tips:**
            - Be friendly and conversational.
            - Keep responses efficient and purposeful.

            Here is the collection you should consider when generating the prompt: {collection}""",
            input_variables=["collection"],
        )
        chain = (
            prompt
            | self.llm
            | StrOutputParser()
        )
        
        logger.info("Generating individual prompts for all collections")
        prompts = {c['collection_name']: chain.invoke({"collection": c}) for c in self.coll_dicts if c['number_docs'] > 0}
        return prompts