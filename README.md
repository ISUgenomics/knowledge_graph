# ISU Knowledge Base — LangGraph Skill Suite

A suite of LangGraph skill plugins that build an Obsidian knowledge vault from ISU research data. Each skill captures a different entity type (people, signals, centers, events) and outputs interlinked markdown notes.

---

## Setup

```bash
pip install -r requirements.txt

ollama pull qwen3-coder:30b
ollama serve
```

Defaults to `qwen3-coder:30b` (30B MoE, 3B active). Pass `--model <name>` to use a different model.

### Vault Setup

Configure the Obsidian vault with graph colors, CSS snippets, and folder structure:

```bash
python skills/shared/setup_vault.py /path/to/vault
python skills/shared/setup_vault.py /path/to/vault --dry-run      # preview
python skills/shared/setup_vault.py /path/to/vault --colors-only   # graph + CSS only
```

Quit Obsidian before running — it overwrites `graph.json` on exit.

---

## Skills

### person-research

Profile people from APIs (OpenAlex, PubMed, ORCID, ISU LDAP, department pages).

```bash
cd skills/person_research
python run.py "Andrew Severin"
python run.py "Andrew Severin" --institution "Iowa State University"
python run.py --input people.tsv          # batch from TSV
```

Output: `vault/people/<slug>/<slug>.md` + `abstracts/*.md` per paper.

### signal-capture

Capture news/blog articles as signal notes with topic and person context.

```bash
cd skills/signal_capture
python run_signal.py --url "https://..." --topic "artificial intelligence"
python run_signal.py --file article.txt --topic ai
python run_signal.py --input urls.txt --skip-existing --topic ai   # batch
```

`--topic` adds keyword-in-context snippets and quote-attributed person snippets.

Output: `vault/signals/<slug>.md` + `raw/<slug>.txt` (original source) + `<slug>-people.tsv`.

#### Batch from ISU News search

```bash
python scripts/scrape_search.py "artificial intelligence" > urls.txt
python run_signal.py --input urls.txt --skip-existing --topic ai
```

#### Backfill existing signals

Update existing notes without re-running the LLM (tag fixes, snippets, raw files):

```bash
python backfill_signals.py --topic ai vault/signals/           # dry run by default
python backfill_signals.py --topic ai --refetch vault/signals/  # fetch raw content
python backfill_signals.py --topic ai vault/signals/ --no-dry-run
```

### center-research

Document research centers/groups from URLs and local files.

```bash
cd skills/center_research
python run_center.py --name "Virtual Reality Applications Center" --url "https://..."
python run_center.py --name "VRAC" --folder /path/to/files
```

Output: `vault/centers/<slug>.md` + `<slug>-members.tsv`.

### event-research

Capture event notes from local folders (agendas, rosters, slides).

```bash
cd skills/event_research
python run_event.py --name "GIF Meeting" --date 2026-05-01 --folder /path/to/files
```

Output: `vault/events/<date>-<slug>/<slug>.md` + `notes/*.md` + `attendees.tsv`.

---

## Shared Utilities

All skills share common scripts in `skills/shared/scripts/`:

| Script | Purpose |
|--------|---------|
| `fetch_with_fallback.py` | URL fetch with gzip decompression and bot-wall hard stop |
| `extract_text.py` | PDF/HTML/DOCX to plain text |
| `extract_snippets.py` | Topic and person snippet extraction with quote-priority |
| `extract_names.py` | Regex name extraction from text |
| `inventory_folder.py` | Recursive folder listing |
| `tag_resolver.py` | Fuzzy-match tags against vault registry (>80% threshold) |
| `verify_extraction.py` | Check extraction completeness |
| `setup_vault.py` | Obsidian vault setup (graph colors, CSS, folders, tag registry) |

---

## Cross-Skill Pipeline

Each skill emits `.tsv` files of discovered people, feeding into person-research:

```
signal-capture  ──>  signals/<slug>-people.tsv  ──>  person-research --input
center-research ──>  centers/<slug>-members.tsv ──>  person-research --input
event-research  ──>  events/<slug>/attendees.tsv ──>  person-research --input
```

---

## Vault Structure

```
vault/
├── people/<slug>/
│   ├── <slug>.md               Person profile
│   └── abstracts/*.md          Per-paper notes with author wiki-links
├── centers/<slug>.md           Center/group note
├── events/<date>-<slug>/
│   ├── <slug>.md               Event note
│   ├── notes/*.md              Discussion topic notes
│   └── attendees.tsv
├── signals/
│   ├── <slug>.md               Signal note
│   └── raw/<slug>.txt          Original source text
├── tags/
│   └── tag-registry.md         Approved tags
└── .obsidian/
    ├── graph.json              Graph node color groups
    ├── snippets/entity-colors.css  Folder color coding
    └── appearance.json
```

Graph node colors: abstracts (lavender), people (teal), signals (coral), events (green), centers (amber), tags (purple).

---

## LangGraph Harness

All skills use the shared harness at `../../harness/`:

```
[plan] -> gather -> execute <-> tools -> verify -> deliver -> END
                                           |
                                     retry (max 3)
```

Strategies: `act` (person, center, signal), `react` (event), `planreact` (reserved).

Override at runtime: `--strategy act|react|planreact`

---

## Key Design Principles

1. **Minimize LLM surface area** — Python handles data fetching, transformation, and formatting. The LLM provides only reasoning fields (~200 tokens: role, summary, tags).
2. **Module-level cache** — Large datasets pass between tools via Python dicts, not LLM context.
3. **Deterministic builders** — All markdown output is assembled by Python, not generated by the LLM.
4. **Tag resolution + sanitization** — `tag_resolver.py` fuzzy-matches against the registry; `_sanitize_tag()` enforces kebab-case.
5. **Raw data preservation** — Original source content saved for future re-processing.

See `BEST_PRACTICES.md` for the full set of 35 lessons learned.

---

## File Structure

```
AgentPlugin/
  requirements.txt
  README.md
  BEST_PRACTICES.md
  harness/
    skill_state.py              SkillState TypedDict + plugin contract
    skill_harness.py            build_skill_graph() factory
  learning/
    01_react_basics/            M1: standalone ReAct loop
    02_skill_harness/           M3: harness demo
  skills/
    person_research/
      plugin.py                 PROMPTS, TOOLS, VERIFY, STRATEGY="act"
      run.py                    CLI entrypoint
      scripts/
        research_person.py      Parallel API fetch
        build_profile.py        Deterministic markdown builder
    signal_capture/
      plugin.py                 PROMPTS, TOOLS, VERIFY, STRATEGY="act"
      run_signal.py             CLI entrypoint (single + batch, --topic)
      backfill_signals.py       Retroactive note updates
      scripts/
        gather_signal.py        URL/file/text fetch + raw save
        build_signal.py         Signal note builder + snippets
        scrape_search.py        ISU News search -> URL list
    center_research/
      plugin.py                 PROMPTS, TOOLS, VERIFY, STRATEGY="act"
      run_center.py             CLI entrypoint
      scripts/
        gather_center.py        URL + folder fetch
        build_center.py         Center note builder
    event_research/
      plugin.py                 PROMPTS, TOOLS, VERIFY, STRATEGY="react"
      run_event.py              CLI entrypoint
      scripts/
        gather_event.py         Folder inventory + URL fetch
        build_event.py          Event note + discussion notes builder
    shared/
      setup_vault.py            Obsidian vault configuration
      scripts/
        fetch_with_fallback.py  URL fetch + bot detection
        extract_text.py         PDF/HTML/DOCX -> text
        extract_snippets.py     Topic/person snippet extraction
        extract_names.py        Name extraction
        inventory_folder.py     Folder listing
        tag_resolver.py         Tag fuzzy matching
        verify_extraction.py    Extraction validation
    vault/                      Obsidian vault (output)
```
