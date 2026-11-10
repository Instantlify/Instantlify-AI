import base64
import io

from django.db import transaction
from pgvector.django import CosineDistance

from .models import KnowledgeChunk, KnowledgeDocument, UsageRecord
from .providers import embedder_for


def split_text(text, size=1800, overlap=200):
    return [
        text[start : start + size]
        for start in range(0, len(text), size - overlap)
        if text[start : start + size].strip()
    ]


def ingest(document, config):
    source = document.source
    if document.file_type == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(base64.b64decode(source)))
        if len(reader.pages) > 100:
            raise ValueError("document_page_limit")
        source = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif document.file_type == "docx":
        from .web_import import docx_text

        source = docx_text(base64.b64decode(source))
    elif document.file_type == "url":
        from .web_import import fetch_page

        _, source = fetch_page(source)
    if not source.strip() or len(source) > 250000:
        raise ValueError("document_size_or_empty")
    chunks = split_text(source)
    provider = embedder_for(config)
    vectors = []
    tokens = 0
    for start in range(0, len(chunks), 16):
        batch, count = provider.embed(chunks[start : start + 16])
        vectors.extend(batch)
        tokens += count
    with transaction.atomic():
        KnowledgeChunk.objects.for_workspace(document.workspace_id).filter(
            document=document
        ).delete()
        for position, (text, vector) in enumerate(zip(chunks, vectors, strict=True)):
            KnowledgeChunk.objects.for_workspace(document.workspace_id).create(
                workspace_id=document.workspace_id,
                document=document,
                position=position,
                text=text,
                embedding=vector,
            )
        KnowledgeDocument.objects.for_workspace(document.workspace_id).filter(
            pk=document.pk
        ).update(status="ready", embedding_model=config.embedding_model)
        record, created = UsageRecord.objects.for_workspace(document.workspace_id).get_or_create(
            key=f"document:{document.id}"
            + (f":revision:{document.source_revision}" if document.source_revision else ""),
            defaults={
                "workspace_id": document.workspace_id,
                "provider": config.provider,
                "model": config.embedding_model,
                "kind": "embedding",
                "input_tokens": tokens,
                "status": "complete",
            },
        )
        if created:
            from apps.billing.services import charge_embedding

            charge_embedding(config, record, tokens)


def retrieve(config, question, key, knowledge_base_id=None):
    chunks = KnowledgeChunk.objects.for_workspace(config.workspace_id).filter(
        document__status="ready", document__embedding_model=config.embedding_model
    )
    if knowledge_base_id:
        chunks = chunks.filter(document__knowledge_base_id=knowledge_base_id)
    if not chunks.exists():
        return []
    vectors, tokens = embedder_for(config).embed([question[:10000]])
    record, created = UsageRecord.objects.for_workspace(config.workspace_id).get_or_create(
        key=key,
        defaults={
            "workspace_id": config.workspace_id,
            "provider": config.provider,
            "model": config.embedding_model,
            "kind": "embedding",
            "input_tokens": tokens,
            "status": "complete",
        },
    )
    if created:
        from apps.billing.services import charge_embedding

        charge_embedding(config, record, tokens)
    return list(chunks.order_by(CosineDistance("embedding", vectors[0]))[:5])
