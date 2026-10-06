"""Cliente mínimo da API interna do n8n local (login + chamadas), usado pelos scripts de configuração."""
import json
import urllib.request

BASE = "http://127.0.0.1:5678"
USUARIO, SENHA = "admin@case.local", "CaseGoGroup2026!"


class N8n:
    def __init__(self):
        r = urllib.request.urlopen(urllib.request.Request(
            BASE + "/rest/login", method="POST", headers={"Content-Type": "application/json"},
            data=json.dumps({"emailOrLdapLoginId": USUARIO, "password": SENHA}).encode()))
        # o cookie vem marcado como "Secure"; em http local precisa ser reenviado manualmente
        self.cookie = "; ".join(c.split(";")[0] for c in r.headers.get_all("Set-Cookie") or [])

    def req(self, metodo: str, caminho: str, corpo=None):
        r = urllib.request.Request(BASE + caminho, method=metodo,
                                   data=json.dumps(corpo).encode() if corpo is not None else None,
                                   headers={"Content-Type": "application/json", "Cookie": self.cookie})
        return json.load(urllib.request.urlopen(r))

    def credencial(self, nome: str, tipo: str, dados: dict) -> str:
        """Cria (ou atualiza) uma credencial pelo nome e devolve o id."""
        ja = [c for c in self.req("GET", "/rest/credentials")["data"] if c["name"] == nome]
        if ja:
            self.req("PATCH", f"/rest/credentials/{ja[0]['id']}", {"name": nome, "type": tipo, "data": dados})
            return ja[0]["id"]
        return self.req("POST", "/rest/credentials", {"name": nome, "type": tipo, "data": dados})["data"]["id"]

    def ativar(self, wid: str) -> None:
        v = self.req("GET", f"/rest/workflows/{wid}")["data"]["versionId"]
        self.req("POST", f"/rest/workflows/{wid}/activate", {"versionId": v})
