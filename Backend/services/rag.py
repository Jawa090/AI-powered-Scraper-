"""Public facade for the contract-tested isolated RAG HTTP client."""
from integrations.rag_client import RAGClient as ContractClient


class RAGClient(ContractClient):
    def search(self, query, top_k=5):
        result = super().search(query, top_k=top_k)
        if isinstance(result, dict) and result.get('error'):
            raise RuntimeError(result['error'].get('code', 'RAG_SEARCH_ERROR'))
        return result.get('hits', []) if isinstance(result, dict) else result


rag_client = RAGClient()
