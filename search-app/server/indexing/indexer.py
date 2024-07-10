from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import GPT4AllEmbeddings
from langchain.indexes import SQLRecordManager, index
from typing import List
from langchain_core.documents import Document
import logging 
from langchain_community.embeddings import HuggingFaceEmbeddings

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


class Indexer():
    def __init__(
            self,
            index_name: str,
            persist_directory: str = './chroma_db',
            embedding_model: str = "nomic-embed-text-v1.5.f16.gguf",
            use_hf_model: bool = False,
            k: int = 3,
            score_treshold: float = 0.6,
        ):
        self.index_name = index_name
        self.embedding_model = embedding_model

        if use_hf_model:
            model_name = self.embedding_model
            model_kwargs = {'device': 'cpu'}
            encode_kwargs = {'normalize_embeddings': False}
            hf = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs=model_kwargs,
                encode_kwargs=encode_kwargs
                )
            self.embedding_function = hf
        else:
            self.embedding_function = GPT4AllEmbeddings(model_name=embedding_model)

        self.vectorstore = Chroma(persist_directory=persist_directory,
                                  embedding_function=self.embedding_function,
                                  collection_name=index_name)
        
        self.namespace = f"chromadb/{index_name}"
        
        self.record_manager = SQLRecordManager(
            self.namespace, db_url="sqlite:///record_manager_cache.sql"
        )
        
        # self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 20})
        self.retriever = self.vectorstore.as_retriever(search_type="similarity_score_threshold",
                                                       search_kwargs={"score_threshold": score_treshold,
                                                                      "k": k},)

        self.record_manager.create_schema()

    def _clear(self):
        """Hacky helper method to clear content. See the `full` mode section to to understand why it works."""
        index([], self.record_manager, self.vectorstore, cleanup="full", source_id_key="source")
        
    def _index(self, 
               documents: List[Document],
               cleanup=None,
               source_id_key: str="url"):
        logging.info(f"Indexing recieved documents - using {self.embedding_model} as embedding model")
        return index(
            documents,  
            self.record_manager,
            self.vectorstore,
            cleanup=cleanup,
            source_id_key=source_id_key,
        )

    def _get_doc_by_id(self,
                       _id: str):
        return self.vectorstore.get(where={"id": _id}).get('ids')
        
    def _delete_doc_from_index(self,
                               _id: str,
                               cleanup=None,
                               source_id_key: str="url"):
        """In order for the record manager to keep track of deleted documents, 
        we need to recreate the index with all documents minus the document to be deleted"""

        contents = self.vectorstore.get().get('documents')

        metadatas = self.vectorstore.get().get('metadatas')

        documents =  [Document(page_content=doc,metadata=meta) for doc, meta in zip(contents, metadatas) if 'id' in  meta.keys() and meta['id'] != _id]

        return index(
            documents,
            self.record_manager,
            self.vectorstore,
            cleanup="full",
            source_id_key=source_id_key,
        )
