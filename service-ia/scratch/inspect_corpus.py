import psycopg2
import json
import os

db_url = os.getenv('DATABASE_URL', 'postgresql://copilot:change_me_db_password@postgres:5432/avaliance')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'source_document' ORDER BY ordinal_position;")
cols = [r[0] for r in cur.fetchall()]

cur.execute("SELECT * FROM source_document ORDER BY id;")
docs = [dict(zip(cols, [str(v) if v is not None else None for v in r])) for r in cur.fetchall()]

# 1. Corpus scopes
cur.execute('SELECT corpus_scope, count(*) FROM doc_chunk GROUP BY corpus_scope;')
scope_counts = dict(cur.fetchall())

# 2. PDF chunk provenance
cur.execute('''
    SELECT count(*),
           count(source_document_id),
           count(source_page),
           count(DISTINCT source_document_id)
    FROM doc_chunk WHERE corpus_scope = 'PDF';
''')
pdf_prov = cur.fetchone()

print(json.dumps({
    'source_document_columns': cols,
    'corpus_scopes': scope_counts,
    'source_documents_summary': {
        'total_count': len(docs),
        'processed': sum(1 for d in docs if d.get('status') == 'PROCESSED'),
        'failed': sum(1 for d in docs if d.get('status') == 'FAILED'),
        'archived': sum(1 for d in docs if d.get('status') == 'ARCHIVED'),
        'pending': sum(1 for d in docs if d.get('status') == 'PENDING'),
    },
    'pdf_provenance': {
        'total_pdf_chunks': pdf_prov[0],
        'with_source_document_id': pdf_prov[1],
        'with_source_page': pdf_prov[2],
        'distinct_documents': pdf_prov[3]
    },
    'source_documents': docs
}, indent=2, ensure_ascii=False))

cur.close()
conn.close()
