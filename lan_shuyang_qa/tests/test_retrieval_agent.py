import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

from app.agents.retrieval import RetrievalAgent


class RetrievalEndpointContractTests(unittest.TestCase):
    def test_search_posts_to_api_retrieval_contract(self):
        original = os.environ.get("RETRIEVAL_URL")
        os.environ.pop("RETRIEVAL_URL", None)
        try:
            agent = RetrievalAgent()
            response = unittest.mock.Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                "results": [
                    {
                        "id": "1",
                        "text": "APT29 used valid accounts.",
                        "source": "CISA",
                        "score": 0.91,
                        "entities": {"actors": ["APT29"]},
                        "graph_paths": ["APT29 -> T1078"],
                    }
                ]
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=response)
                result = asyncio.run(agent.search("APT29", top_k=1))

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].source, "CISA")
            called_url = mock_client.return_value.__aenter__.return_value.post.call_args.args[0]
            self.assertTrue(called_url.endswith("/api/retrieval"))
            self.assertEqual(
                mock_client.return_value.__aenter__.return_value.post.call_args.kwargs["json"],
                {"query": "APT29", "top_k": 1},
            )
        finally:
            if original is None:
                os.environ.pop("RETRIEVAL_URL", None)
            else:
                os.environ["RETRIEVAL_URL"] = original


if __name__ == "__main__":
    unittest.main()
