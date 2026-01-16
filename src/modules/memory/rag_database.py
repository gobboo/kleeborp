import asyncio
from uuid import uuid4
import chromadb


class RAGDatabase:
    def __init__(self, config):
        self.database = chromadb.PersistentClient(
            path=config["chroma_path"],
            settings=chromadb.Settings(anonymized_telemetry=False),
        )

        self.collection: chromadb.Collection = None
        self.config = config

    async def initialize(self):
        self.collection = await asyncio.to_thread(self._create_if_not_exists_sync)

    async def query_relevant_entries(self, input: str) -> list[str]:
        return await asyncio.to_thread(self._query_relevant_entries_sync, input)

    async def upsert(self, document: str):
        return await asyncio.to_thread(self._upsert_sync, document)

    def _create_if_not_exists_sync(self):
        return self.database.create_collection("memories", get_or_create=True)

    def _query_relevant_entries_sync(self, input: str) -> list[str]:
        results = self.collection.query(
            query_texts=[input], n_results=3, include=["documents", "distances"]
        )

        docs = results["documents"][0]
        dists = results["distances"][0]

        MAX_DISTANCE = 1.0 - self.config["minimum_distance"]

        return_results = []

        for doc, dist in zip(docs, dists):
            if dist <= MAX_DISTANCE:
                return_results.append(doc)

        return return_results

    def _upsert_sync(self, document: str):
        self.collection.upsert(
            ids=[str(uuid4())], documents=[document], metadatas=[{"type": "short-term"}]
        )
