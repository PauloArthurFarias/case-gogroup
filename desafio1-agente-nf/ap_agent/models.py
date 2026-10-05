"""Modelos de dados (Pydantic) compartilhados por extração, validação e agente."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TipoDocumento(str, Enum):
    NFE_XML = "NFE_XML"
    DANFE_PDF = "DANFE_PDF"
    BOLETO = "BOLETO"


class Severidade(str, Enum):
    OK = "OK"
    ALERTA = "ALERTA"      # exige revisão humana
    CRITICO = "CRITICO"    # bloqueia o pagamento


class Status(str, Enum):
    APROVADO = "APROVADO"
    REVISAO = "REVISAO"
    REJEITADO = "REJEITADO"
    PAGO = "PAGO"


class Item(BaseModel):
    codigo: str = ""
    descricao: str
    quantidade: float
    valor_unitario: float
    valor_total: float


class DocumentoFiscal(BaseModel):
    """Representação normalizada de uma NF-e/DANFE ou boleto."""
    tipo: TipoDocumento
    arquivo: str = ""
    chave_acesso: Optional[str] = Field(None, description="44 dígitos da NF-e")
    numero: Optional[str] = None
    serie: Optional[str] = None
    data_emissao: Optional[date] = None
    cnpj_emitente: str
    nome_emitente: str = ""
    cnpj_destinatario: Optional[str] = None
    pedido_compra: Optional[str] = Field(None, description="Ex.: PC-1001")
    itens: list[Item] = []
    valor_produtos: Optional[float] = None
    valor_total: float
    data_vencimento: Optional[date] = None
    linha_digitavel: Optional[str] = None
    confianca_extracao: float = 1.0
    metodo_extracao: str = "xml"


class ExtracaoLLM(BaseModel):
    """Schema que o Claude preenche ao ler um PDF (structured output)."""
    tipo: TipoDocumento
    chave_acesso: Optional[str] = None
    numero: Optional[str] = None
    serie: Optional[str] = None
    data_emissao: Optional[str] = Field(None, description="AAAA-MM-DD")
    cnpj_emitente: str = Field(description="Somente dígitos. Em boleto, CNPJ do beneficiário")
    nome_emitente: str
    cnpj_destinatario: Optional[str] = None
    pedido_compra: Optional[str] = None
    itens: list[Item]
    valor_produtos: Optional[float] = None
    valor_total: float
    data_vencimento: Optional[str] = Field(None, description="AAAA-MM-DD")
    linha_digitavel: Optional[str] = Field(None, description="Somente dígitos")
    confianca: float = Field(description="0 a 1: sua confiança de que todos os campos estão corretos")


class Verificacao(BaseModel):
    regra: str
    severidade: Severidade
    mensagem: str


class Decisao(BaseModel):
    status: Status
    justificativa: str
    decidido_por: str  # "regras" | "agente:<modelo>"
