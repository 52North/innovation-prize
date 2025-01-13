import time
from UltraDict import UltraDict
from indexing.indexer import Indexer
from loguru import logger

class IndexerManager:
    def __init__(self):
        self.indexes = UltraDict(name="indexer_manager")
        self.lock_timeout = 600 # Lock timeout in seconds

    def _wait_for_initialization(self):
        start_time = time.time()
        while time.time() - start_time < self.lock_timeout:
            if "init_lock" not in self.indexes:
                return
            time.sleep(0.1)
        raise TimeoutError("Initialization timed out")

    def initialize(self):
        if self.indexes.get("init_lock", False):
            # If we couldn't acquire the lock, wait for initialization
            logger.debug("Indexes are being initialized ...")
            self._wait_for_initialization()
            return
        self.indexes["init_lock"] = True
        
        try:
            logger.debug("Initializing indexes...")
            self.indexes = {
                "pygeoapi": Indexer(index_name="pygeoapi", score_treshold=0.4, k=20),
                "geojson": Indexer(index_name="geojson", score_treshold=0.4, k=20)
            }
        finally:
            # Release the lock
            if "init_lock" in self.indexes:
                del self.indexes["init_lock"]

    def get_indexes(self):
        return self.indexes

# Global Object Pattern
indexer_manager = IndexerManager()
