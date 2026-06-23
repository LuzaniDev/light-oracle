from typing import List


class HyDEGenerator:
    def __init__(self):
        self.templates = {
            "fact": "Informação sobre {query}.",
            "value": "O valor de {query} é um dado específico encontrado nos documentos.",
            "list": "A lista de {query} contém os seguintes itens: ",
            "procedure": "O procedimento para {query} envolve os seguintes passos: ",
            "comparison": "A comparação entre {query} mostra diferenças e semelhanças.",
            "default": "Documento que contém informações relevantes sobre {query}.",
        }

    def generate(self, query: str, query_type: str = "default") -> str:
        template = self.templates.get(query_type, self.templates["default"])
        return template.format(query=query)

    def generate_hypothetical(self, query: str) -> str:
        return f"Este documento contém informações relevantes sobre: {query}"
