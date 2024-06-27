import asyncio
import aiohttp
import logging
from typing import List, Dict
from langchain.schema import Document
from config.config import Config

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)

config = Config('./config/config.json')

class PyGeoAPI:
    def __init__(self, urls: List[str] = None):
        if urls:
            self.urls = urls
        else:
            self.urls = config.pygeoapi_instances

    async def _get_queryables(self, session: aiohttp.ClientSession, collection_id: str, base_url: str) -> dict:
        """
        Get all queryables of a collection asynchronously.

        args: collection_id: str -> ID of collection
        """
        queryables_url = f'{base_url}/collections/{collection_id}/queryables'
        params = {'f': 'json'}

        async with session.get(url=queryables_url, params=params) as response:
            if response.status == 200:
                queryables = await response.json()
                return queryables['properties']
            return {}

    async def _get_collections(self, base_url: str) -> List[dict]:
        """
        Get all collections of a pygeoapi instance asynchronously.
        """
        logging.info(f"Fetching collections of pygeoapi instance: {base_url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(f'{base_url}/collections/') as response:
                if response.status == 200:
                    collections = await response.json()
                    logging.debug(collections)

                    tasks = [
                        self._create_collection_info(session, collection, base_url)
                        for collection in collections['collections']
                    ]
                    collection_info = await asyncio.gather(*tasks)
                    return collection_info
                return []

    async def _create_collection_info(self, session: aiohttp.ClientSession, collection: dict, base_url: str) -> dict:
        queryables = await self._get_queryables(session, collection['id'], base_url)
        return {
            'id': collection['id'],
            'title': collection['title'],
            'description': collection['description'],
            'keywords': collection['keywords'],
            'extent': collection['extent'],
            'queryables': queryables
        }

    def _generate_docs(self, base_url:str, collections: List[dict]) -> List[Document]:
        """
        Converts collections in JSON format to a list of Documents to be loaded to a vector store.
        """
        logging.info("Converting collections to list of documents")
        docs = [Document(page_content=f"Title: {doc['title']}\n Description: {doc['description']}"\
                         f"\n Keywords: {doc['keywords']}\n Queryables: {[q for q in list(doc['queryables'].keys())]}\n Extent: {doc['extent']}", 
                         metadata={"id": doc["id"],
                                   "title": doc["title"],
                                   "url": f"{base_url}/collections/{doc['id']}",
                                   "extent": str(doc["extent"])}) for doc in collections]
        return docs

    async def get_collections_and_generate_docs(self, url) -> Document:
        collections = await self._get_collections(url)
        docs = self._generate_docs(url, collections)
        return docs

    async def get_docs_for_all_instances(self) -> List[Document]:
        tasks = [self.get_collections_and_generate_docs(url) for url in self.urls]
        all_docs = await asyncio.gather(*tasks)
        return all_docs[0]