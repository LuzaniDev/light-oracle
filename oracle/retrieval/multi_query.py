from typing import List


class MultiQueryGenerator:
    def __init__(self, num_queries: int = 3):
        self.num_queries = num_queries

    def generate(self, query: str) -> List[str]:
        queries = [query]
        if self.num_queries >= 2:
            queries.append(f"informações sobre {query.lower()}")
        if self.num_queries >= 3:
            queries.append(f"o que diz sobre {query.lower()}")
        if self.num_queries >= 4:
            queries.append(f"detalhes: {query.lower()}")
        if self.num_queries >= 5:
            queries.append(f"resultados para {query.lower()}")
        return queries[:self.num_queries]
