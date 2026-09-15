# Working documents

Put real standards documents here. **Everything in this folder except this file
is ignored by git**, so nothing you drop here can reach the public site.

```bash
cp ~/Downloads/some-state-standards.csv service/documents/
curl -X POST http://localhost:8000/api/standards-sets/characterize \
  -F "file=@service/documents/some-state-standards.csv"
```

`service/sample_documents/` is the opposite: it is committed and published, and
holds only the invented DEMO file. Do not put a real document there.

## What happens to the data

Ingested standards go into Postgres, in a Docker volume on your machine. They do
not touch git. Running a real framework through the tool is safe.

Committing one is the thing to think about — not because state standards are
secret, they are published documents, but because a coverage percentage against
a named real state, sitting in a public repository, is a claim. The briefing
leaves that decision open on purpose.
