"""Leitura dos manuais em PDF e chunking.

O carregamento usa o ``PyPDFLoader`` do LangChain (um ``Document`` por pagina) e a quebra usa o
``RecursiveCharacterTextSplitter``, que tenta cortar primeiro em paragrafo, depois em linha, depois
em frase: um passo a passo dificilmente e partido no meio.

Dois cuidados que melhoram a busca:

* cabecalhos e rodapes repetidos em todas as paginas sao removidos antes do chunking (senao todo
  chunk "fala" do titulo do manual e a busca perde contraste);
* o texto e dividido primeiro nos titulos numerados ("2.3 Primeiro acesso"), e so depois por
  tamanho: um chunk nunca mistura duas secoes, e cada um guarda a secao a que pertence. A secao
  entra no texto indexado e na citacao devolvida ao usuario.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# "3 Titulo", "3.2 Titulo", "3.2.1 Titulo": numero sem ponto final, titulo comeca com maiuscula.
# "5. Clique em Salvar" (numero seguido de ponto) e item de lista, nao titulo.
_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\s+([A-ZÀ-Ý][^\n]{2,80})$")
_PAGE_NUMBER = re.compile(r"^(?:p[aá]gina\s+)?\d{1,4}(?:\s*(?:/|de|of)\s*\d{1,4})?$", re.IGNORECASE)
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_TITLE_ONLY_MAX_CHARS = 90
SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " ", ""]


def load_pdf_pages(path: Path) -> list[Document]:
    """Um ``Document`` por pagina, com ``source`` (nome do arquivo) e ``page`` (base 1) nos metadados."""
    pages = PyPDFLoader(str(path)).load()
    for page in pages:
        page.metadata = {"source": Path(path).name, "page": int(page.metadata.get("page", 0)) + 1}
    return pages


def _repeated_lines(pages: list[Document], min_share: float = 0.6) -> set[str]:
    """Linhas que se repetem na maioria das paginas: cabecalho e rodape."""
    if len(pages) < 3:
        return set()
    counter: Counter[str] = Counter()
    for page in pages:
        lines = [line.strip() for line in page.page_content.splitlines() if line.strip()]
        counter.update(set(lines[:2] + lines[-2:]))
    return {line for line, count in counter.items() if count / len(pages) >= min_share}


def clean_pages(pages: list[Document]) -> list[Document]:
    boilerplate = _repeated_lines(pages)
    cleaned: list[Document] = []
    for page in pages:
        lines = []
        for line in page.page_content.splitlines():
            stripped = _SPACES.sub(" ", line).strip()
            if stripped in boilerplate or _PAGE_NUMBER.match(stripped):
                continue
            lines.append(stripped)
        text = _HYPHEN_BREAK.sub(r"\1\2", "\n".join(lines))
        text = _BLANK_LINES.sub("\n\n", text).strip()
        if text:
            cleaned.append(Document(page_content=text, metadata=dict(page.metadata)))
    return cleaned


def _headings(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    offset = 0
    for line in text.split("\n"):
        match = _HEADING.match(line.strip())
        if match and not line.rstrip().endswith((".", ":", ";", ",")):
            found.append((offset, f"{match.group(1)} {match.group(2).strip()}"))
        offset += len(line) + 1
    return found


def _sections(text: str, inherited: str) -> list[tuple[str, str]]:
    """Divide o texto de uma pagina em ``(secao, conteudo)`` nos titulos numerados.

    O texto antes do primeiro titulo continua a secao herdada da pagina anterior. Um titulo sem
    corpo (titulo de capitulo seguido direto de um subtitulo) e anexado a secao seguinte, para nao
    virar um chunk que so contem o titulo.
    """
    headings = _headings(text)
    starts_with_heading = bool(headings) and headings[0][0] == 0
    bounds = [0, *[offset for offset, _ in headings if offset > 0], len(text)]
    titles = [headings[0][1] if starts_with_heading else inherited]
    titles += [title for offset, title in headings if offset > 0]

    sections: list[tuple[str, str]] = []
    carry = ""
    for title, begin, finish in zip(titles, bounds[:-1], bounds[1:], strict=True):
        body = text[begin:finish].strip()
        if not body:
            continue
        if "\n" not in body and len(body) <= _TITLE_ONLY_MAX_CHARS and body == title:
            carry = f"{carry}{body}\n"
            continue
        sections.append((title, carry + body))
        carry = ""
    if carry.strip():
        sections.append((titles[-1], carry.strip()))
    return sections


def split_pages(pages: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    """Quebra as paginas em chunks, sem atravessar secoes, e anota secao e ``chunk_id`` em cada um."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=SEPARATORS, add_start_index=True
    )
    chunks: list[Document] = []
    current_section = ""
    for page in pages:
        for section, body in _sections(page.page_content, current_section):
            current_section = section
            for chunk in splitter.split_documents([Document(page_content=body, metadata=dict(page.metadata))]):
                start = int(chunk.metadata.pop("start_index", 0))
                key = f"{chunk.metadata['source']}|{chunk.metadata['page']}|{section}|{start}|{chunk.page_content}"
                chunk.metadata.update(section=section, chunk_id=hashlib.sha256(key.encode()).hexdigest()[:12])
                chunks.append(chunk)
    return chunks


def load_manuals(directory: Path, chunk_size: int, chunk_overlap: int) -> list[Document]:
    """Carrega e quebra todos os PDFs de um diretorio."""
    paths = sorted(Path(directory).glob("*.pdf"))
    if not paths:
        raise FileNotFoundError(f"nenhum PDF encontrado em {directory}")
    chunks: list[Document] = []
    for path in paths:
        pages = clean_pages(load_pdf_pages(path))
        document_chunks = split_pages(pages, chunk_size, chunk_overlap)
        logger.info("manual %s: %d paginas, %d chunks", path.name, len(pages), len(document_chunks))
        chunks.extend(document_chunks)
    return chunks
