# AZ Sprint — Standards and Curriculum Pipeline

**Purpose.** This document moves the standards and curriculum work into a new project that has no memory of it. It records what we built, what we decided, what we ran, and what is still open. Read it before you build anything in this area.

**Compiled:** 15 September 2026 · CodeAI / Code.org
**Source:** prior chat sessions (July–September 2026), the installed skill files, and the handover document *Curriculum corpus and standards mapping* (September 2026).

**Revision 3, 15 September 2026.** Added *Rules, examples, and the anchor*. Read that section first.

**Revision 2, 15 September 2026.** Section 1 was rewritten from the handover. Sections 3, 4, 5, and the open questions were corrected where the corpus changes what is true.

**Language.** This document follows Simplified Technical English (ASD-STE100) rules: short sentences, active voice, one idea per sentence, one word for each meaning. The full STE100 approved-word list is proprietary, so this follows the rules and the spirit. It is not certified compliant.

---

## Terms

Use these words. Do not use synonyms.

| Term | Meaning |
|---|---|
| **standards** | Any list a district must teach. This includes state CS standards, CTE standards, ISTE, industry lists, and single-course objective sets. |
| **standards set** | One document of standards. A state can publish more than one. |
| **align** | To show which standards a course teaches, and how deeply. Do not write "map", "crosswalk", or "reconcile" for this action. |
| **boundary** | The note that says what counts as teaching a standard, and what does not count. |
| **provenance** | Where a boundary came from: the source document, a draft, or a draft that a person checked. |
| **evidence** | The specific student task that proves a course teaches a standard. |
| **record** | One row that joins one standard to one lesson, with a level and evidence. |
| **AIF** | AI Foundations. A full-year high school course. Two semesters, 12 units. |
| **AID** | AI Discoveries. A middle grades course. |
| **RP** | Regional Partner. |
| **unit / script** | One unit of a course. The unit of serialization. Identified by `script_name`. |
| **level** | One screen a student works on. |
| **sublevel** | A level nested inside another, for example one option of a choice. |
| **corpus** | The extracted, structured record of the curriculum. The evidence base for alignment. |
| **Levelbuilder** | The tool authors use to edit curriculum. |
| **scoop** | The nightly job that commits serialized curriculum to git. |
| **seeding** | The task that writes serialized files into a database. |
| **DTS / DTP** | Deploy to staging / deploy to production. |
| **KPAS** | Knowledge and Performance Anchor Standards, in California CTE. |

---

## Rules, examples, and the anchor

This document names many states and frameworks. They are not all the same kind of thing. Read this before you read the rest, so you do not mistake past work for configuration.

**Nothing in this document is state-specific configuration. No state is built into any tool.**

### Three kinds of named thing

**1. Rules.** The tools obey these. Change a rule and you change how every run behaves.

Rules are the canonical schema fields, the four rating levels, the seven verification checks, the boundary provenance gate, the file-naming patterns, and the identifier rules (`stable_id`, `script_name`, `content_hash`). These apply to every framework and every course.

**2. Examples.** These are finished work, recorded so you can see how the rules behave on a real document. **No tool reads them. Nothing depends on them.**

Every mention of Texas, California, Oklahoma, North Carolina, and Indiana is in this class. So is every count, percentage, and file name from those runs. They exist here for three reasons: to show what good output looks like, to record decisions made under pressure that you should not have to re-make, and to warn you about traps found the hard way.

The same is true of `NC_CS10_2025-26.json` and similar strings in the skill files. They illustrate a naming pattern. They are not a lookup.

**3. The anchor.** CSTA 2026 is deliberately built in. This is intended, not an oversight.

CSTA is the reference the ingestion process drafts boundaries against, and the default standards set when no other file is given. State frameworks rarely ship boundary language; CSTA does. Drafting against a fixed, well-specified reference is what makes the boundaries traceable and comparable across states. The `nearest_csta` field and the `csta-alignment` skill name both follow from this choice.

Two things the anchor does not mean:

- It does not mean a run must involve CSTA. The alignment engine evaluates against **any** standards file that conforms to the schema.
- It does not make `nearest_csta` a crosswalk. It is a drafting aid and an audit trail.

### The one thing to fix

The schema currently applies silent defaults. When the identity fields are absent, a consumer defaults `framework` to `CSTA` and `framework_year` to `2026`. So a file that loses its identity trio does not fail. It becomes a CSTA file, quietly, and a wrong label can reach a deliverable.

Make the identity trio required, and fail loudly when it is missing. The anchor should be a default you choose, not a default you inherit by accident.

### How to tell them apart while reading

- A **rule** says what the tool does, in the present tense: "Copy each statement word for word."
- An **example** names a state and a number: "AIF to Texas CS I — 79% coverage."
- The **anchor** is CSTA, and it is named as the reference or the default.

---

## 0. The pipeline in one view

Six stages. Each stage gives its output to the next stage.

```
1. Curriculum data  ──┐
                      ├──►  3. Align  ──►  4. Store  ──►  5. Internal tool  ──►  6. External tool
2. Standards data  ───┘                      (schema)        (review, edit)        (public view)
```

Two rules control the whole pipeline.

1. **A person checks the boundaries one time for each standards set.** Work for internal use can run before this check. Work that a district sees must wait for it.
2. **The curriculum is locked.** The pipeline reports what the materials teach and what they do not teach. It does not recommend changes to the curriculum.

---

## 1. Sourcing curriculum data

**This section was replaced on 15 September 2026.** The snapshot pack described in the first draft is superseded for standards mapping. A structured corpus extracted from the `code-dot-org` repository replaces it. The source is the handover document *Curriculum corpus and standards mapping*.

**The snapshot pack is not retired.** It remains a good model for slide production and PL experience design, where a small curated corpus of readable unit files is easier to work with than 23 MB of records. Keep it for those uses. Do not use it as the evidence base for alignment.

### Why the change

The old method read lesson plan PDF files and recorded matches in a spreadsheet. It has three faults.

- PDF files are rendered output. They are large, English only, and they lose the structure of the lesson.
- A spreadsheet cannot tell you when the curriculum changed. The alignment goes stale and nobody knows which rows to re-check.
- The work cannot be repeated cheaply. Each new state starts again.

The corpus replaces the PDF step with a structured record that refreshes from the platform and reports what changed.

### Where the content lives

Read this before you change any tool.

All lesson content is stored as records in a MySQL database. The website reads from that database. It does not read from files. The records form a hierarchy:

```
CourseOffering -> CourseVersion -> UnitGroup (course) -> Unit (script)
  -> LessonGroup -> Lesson
      -> Objective
      -> LessonActivity -> ActivitySection -> ScriptLevel -> Level
```

Shared catalogs sit beside this: Resource, Vocabulary, Framework, Standard.

Authors edit these records in a tool named Levelbuilder. When an author saves, the database record updates, and the record is written out as a file in a git checkout. The file is one per unit:

```
dashboard/config/scripts_json/<unit>.script_json
```

That file holds the complete teacher-facing lesson plan for every lesson in the unit.

Content reaches the website by this path:

```
Levelbuilder database
  -> serialized to .script_json file
  -> nightly "scoop" commits and pushes the file to git
  -> DTS merges it into the staging branch
  -> seeding writes the file into the staging database
  -> DTP
  -> seeding writes the file into the production database
  -> the website serves from the production database
```

Seeding is the task `seed:scripts`. It is incremental and skips a file whose md5 has not changed.

Two consequences:

- The files are a faithful copy of the live records. They are usually less than one day behind.
- The files are not the live data. For "what a teacher sees right now", the production database is the only answer.

### Student instructions live somewhere else

Lesson plans are teacher-facing. The screens students read are separate records called levels. Level content sits in two directories, in two formats.

| Directory | Format | How to find a level |
|---|---|---|
| `dashboard/config/levels/` | XML wrapper with a JSON config inside a CDATA block | The file name is the level name |
| `dashboard/config/scripts/` | DSL text files (`.multi`, `.external`, `.bubble_choice`, `.level_group`, `.match`) | The file name is **sanitized** and does not match. Read the `name '...'` line inside the file |

**This is the most common way to get the extraction wrong.** 462 of the 1,606 level references in AIF and AID sit in the second directory. That is 29 percent. They are invisible if you read the first directory only.

### The corpus

Source: `code-dot-org` repository, `staging` branch, commit `095e20d1c050`.

| Item | Count |
|---|---|
| Courses | 4 |
| Units | 24 distinct |
| Lessons with a lesson plan | 315 |
| Lessons with on-screen student content | 286 |
| Level records, including sublevels | 2,979 |
| Words of student instructions | 317,793 |
| Instructional minutes | 18,315 |
| Resource links | 1,344 (133 are answer keys) |
| Standard references | 1,255, all resolved to statement text |

| Course | Units | Lessons |
|---|---|---|
| AIF Semester 1: Exploring AI and CS | 8 | 88 |
| AIF Semester 2: Designing and Building with AI | 6 | 58 |
| AI Discoveries (AID) | 9 | 167 |
| AIF Year 1 (full-year variant) | 12 | 121 |

Counts overlap. Units are shared between courses. AIF Year 1 reuses Semester 1 and Semester 2 units and adds one of its own. Each unit is extracted once and attributed to every course that includes it.

Standard references already present in the curriculum, by framework: CSTA 2026 (424), CSTA 2017 (789), AI4K12 2021 (42).

**Note the unit counts against the old pack.** The pack recorded AIF S1 as 6 units and AIF S2 as 6. The corpus reports AIF S1 as 8 units and a separate 12-unit full-year variant. Trust the corpus. The pack is a curated subset, not the course structure.

### Size

23 MB unpacked, about 1.4 million tokens. Size does not matter, because mapping runs one lesson at a time.

| | Typical | Largest |
|---|---|---|
| Lesson plan | 12 KB | 49 KB |
| Student instructions | 9 KB | 47 KB |
| Both together | 21 KB | 96 KB |

A typical lesson is about 5,000 tokens. Repeated text is 4 percent of the corpus.

### The tools

| Tool | Purpose |
|---|---|
| `extract_curriculum.py` | Reads the unit files. Writes one lesson-plan record per lesson. |
| `extract_levels.py` | Reads the level files. Attaches student instructions to each lesson. |
| `distil_lesson.py` | Writes a short, actionable record of student actions. **Prototype. One lesson only.** |
| `join_mapping.py` | Adds durable lesson identity to an existing mapping file. |
| `coverage_report.py` | Turns a standards catalog plus a mapping into a coverage report. |

### How to rebuild

Get the source with a blobless sparse clone. This takes about 1.5 GB.

```bash
git clone --filter=blob:none --no-checkout --depth 1 -b staging \
  https://github.com/code-dot-org/code-dot-org.git cdo
cd cdo
git sparse-checkout init --cone
git sparse-checkout set \
  dashboard/config/courses \
  dashboard/config/scripts_json \
  dashboard/config/course_offerings \
  dashboard/config/standards \
  dashboard/config/levels \
  dashboard/config/scripts
git checkout staging
cd ..
```

`git sparse-checkout set` **replaces** the directory list. It does not add to it. List every directory each time.

Extract in this order. The second tool reads the first tool's manifest.

```bash
python3 extract_curriculum.py --repo ./cdo --out ./out
python3 extract_levels.py     --repo ./cdo --corpus ./out
```

Scope a run to other courses with a flag:

```bash
python3 extract_curriculum.py --repo ./cdo --out ./out --courses csd-2026,csp-2026
```

### How to detect change

**Do not build a monitor.** The repository is already a versioned record.

Keep the `out/` directory in its own git repository. Commit after every run. Then `git diff` is the change report. It shows which lessons changed and what text changed inside them.

Each lesson also carries a `content_hash`. This fingerprints the content fields only; provenance and timestamps are excluded. The hash changes when the content changes, and not otherwise. **This is the mechanism that answers the version-keying requirement.**

Do not use the unit's `serialized_at` for this. It is per unit. One edited section restamps the whole unit, so it cannot tell you which lesson changed.

### The corpus files

```
manifest.csv            one row per lesson. Open this first.
manifest.json           same, plus course and unit metadata and provenance
warnings.json           findings from the lesson-plan run
levels_manifest.csv     one row per lesson, student-content counts
levels_warnings.json    findings from the student-content run

lessons/<unit>/NN-<slug>.md            readable lesson plan
lessons/<unit>/NN-<slug>.json          lesson-plan record
levels/<unit>/NN-<slug>.levels.md      student instructions, in student order
levels/<unit>/NN-<slug>.levels.json    student-instruction record
distilled/<unit>/NN-<slug>.actions.md  short action record (one sample only)
```

**Lesson-plan record fields:** identity (`stable_id`, `lesson_key`, `lesson_name`, `relative_position`, `absolute_position`); prose (`overview_md`, `student_overview_md`, `purpose_md`, `preparation_md`, `assessment_opportunities_md`); alignment inputs (`objectives`, `standards`, `opportunity_standards`, `learning_goals`); the teaching guide as `activities[] -> sections[] -> levels[]` with `description_md`, typed `tips`, `is_remarks`, `progression_name`, durations; materials (`vocabulary`, `resources` with name, URL, audience, `is_answer_key`); and change tracking (`content_hash`, `provenance`).

**Student-instruction record fields, per level, in the order a student meets it:** `student_text`, `answer_options` with the correct one marked, `sublevels`, `context` (activity, section, progression, assessment flag, bonus flag), `level_type`, `title`, `teacher_markdown`, `ai_tutor_available`, `submittable`, `has_starter_code`, `has_validation`, `content_hash`, `word_count`.

### Identifiers

- `stable_id` is `script_name::lesson_key`. **Use it for joins.**
- `lesson_key` is set when the lesson is created. **It does not follow renames.** Treat it as opaque. Never display it as a label.
- `lesson_name` is the current title. Use it for display.
- `script_name` is the unit. It is stable and unique. **Record it. Never record a unit number.**

### Findings that can cause a wrong claim

Each of these was discovered during the build. Each can produce a false result that looks like success.

**Parent levels hold no text of their own.** `bubble_choice` and `level_group` levels, and code levels with `contained_level_names`, keep their content in their children. Reading parents only found 126,454 words. Reading children as well found 317,793. The missing 60 percent was almost all question text and activity instructions. The extraction completes and reports no failure, so this error is silent.

**Lesson keys go stale.** Ten lessons carry keys that are former titles. Eight are in AID Unit 1 (`thinking-critically-about-ai-2026`), which was rewritten and resequenced. Two also changed position, so the number in the key contradicts the number in the title.

| Key (former title) | Current name |
|---|---|
| `Lesson 4: Guidelines for Working with AI` | Lesson 5: Creating a Chatbot |
| `Lesson 5: Trust and Credibility` | Lesson 4: AI-Generated Images |

**Any older AID Unit 1 alignment that refers to lessons by title or number is probably mismapped.** AID Unit 1 is a current priority for state alignment updates. Check this before the next state submission.

**AIF Semester 2 unit numbers are inconsistent.** The first four units have an empty unit number. The last two are numbered 1 and 2.

| Position in course | Unit | Displayed number |
|---|---|---|
| 1 | AI-Generated Design | *(blank)* |
| 2 | AI and Algorithmic Decisions | *(blank)* |
| 3 | Building Data-Driven Systems with AI | *(blank)* |
| 4 | Iterating with AI | *(blank)* |
| 5 | Designing Reliable Apps with AI and APIs | 1 |
| 6 | Web Apps with AI Capstone Project | 2 |

So "Semester 2, Unit 2" is ambiguous. By course order it is AI and Algorithmic Decisions. By the number on screen it is the capstone. Always record `script_name`.

**Some lessons are much larger than a lesson.** The capstone unit (`web-apps-with-ai-capstone-project-2026`) holds one lesson that runs ten days and contains milestones. The earlier California mapping treated those days as lessons; seven rows point at "Lesson 4", which does not exist. The corpus holds the milestone names. The mapping needs a level below the lesson to hold them. **Not yet built.**

**Choice levels.** Many lessons offer a choice of scenario. Each student completes one option, not all. A claim resting on one option is met by a fraction of the class. The raw corpus does not make this obvious. The distilled record does.

**60 lessons have no lesson plan.** They are assessment shells, end-of-unit surveys, and pre-assessments, flagged `has_lesson_plan: false` and skipped. They still occupy lesson positions, so `relative_position` and `absolute_position` can differ.

**Five project lessons have no authored objective.** There is nothing to anchor a forward alignment claim on.

**Six levels have no student text.** Five are AI for Oceans interactive levels; one is a video. The activity is the interface, not words. This is correct, not a fault.

**Curriculum content may move.** The seeding task reads curriculum config from an overridable directory variable (`CURRICULUM_CONTENT_DIR`), and engineering has discussed moving curriculum content out of the main repository. Both extractors keep the paths in one place, so only that part must change.

### Not yet collected

- Worksheets and slide decks are Google Docs and Google Slides. The lesson record holds the links and the audience tag, but not the content.
- Some slide decks also exist in the repository at `config/slides/.../slides.json`. Not checked.
- **Settle who may see the corpus before it holds this content.** 133 of the linked documents are answer keys restricted to verified teachers.

### The distilled layer (prototype)

The reason is signal, not size. Much of a lesson plan is teacher choreography — "Review the lesson objectives", "Direct students to Stand and Swap" — which is necessary for a teacher and useless for alignment. The authored objectives are too general to tell a reviewer what the student produces.

For each lesson the distilled record holds: the stated objectives; whether the objectives match what students do, with the supporting steps and who does the work; what every student does, as observable steps from the student screens; the choice points, marking which steps are shared and which belong to one option; the results students must verify; what students produce; what is checked; the concepts present; and the questions the tool cannot answer. Every item names the level it came from, so a claim can always be checked.

One sample exists: `out/distilled/ai-and-algorithmic-decisions-2026/05-lesson-5-making-decisions-with-ifelse.actions.md`, 7.4 KB from 24 KB of source.

Limits to know:

- The tool finds student actions by reading "Do This" headings. This curriculum uses them consistently. Lessons written another way produce a thinner record.
- Objectives are matched to actions by shared wording. The verdicts are prompts to check, not conclusions.
- Absences are not invented. The tool asks the question and leaves it for a person.
- **This layer is derived. It must never replace the corpus.** Rebuild it when a lesson's hash changes, or it goes stale in silence.

---

## 2. Standards ingestion

The skill is `standards-ingestion`. It converts a raw standards document into our format.

The hard part is not parsing. The hard part is **drafting boundaries**. CSTA 2026 ships boundary statements. State frameworks almost never do. Ingestion quality is judged on boundary quality.

### Procedure

1. **Read the source document.** The format can be PDF, CSV, XLSX, DOCX, or pasted text.
2. **Characterize the document.** Find the identifier scheme and its anatomy. Find the hierarchy: concepts, strands, subconcepts, grade bands. Look in the appendixes; state PDFs often bury half the standards there.
3. **Set the identity trio.** These three fields must be unique across all sets we hold.
   - `framework` — the issuing body. Example: `NC`, `OK`, `CA`, `TX`, `CSTA`.
   - `standard_set` — *which document* within that body. Example: `CS10`, `CS-Standards`, `CTE-ICT`. For CSTA, use the vintage.
   - `set_type` — `course_objectives` for a single weighted course blueprint, or `standards` for an umbrella framework.
   This trio is what keeps "AIF to NC CS10" from ever merging with "AIF to NC CS-Standards".
4. **Report the characterization to the user. Get agreement on scope. Then continue.**
5. **Extract verbatim.** Copy each statement word for word. Never paraphrase. Never invent or normalize an identifier. If the source has no identifiers, build them from the document's own structure and record the rule in `schema_notes`.
6. **Reconcile the count.** State the number extracted. Compare it to the count the document claims. A silent extraction gap poisons everything downstream.
7. **Find nearest CSTA analogs.** Record 0 to 3 CSTA 2026 ids in `nearest_csta`. Match on meaning, not vocabulary. An empty list is an honest result. This is a drafting aid and an audit trail. **It is not a validated crosswalk.**
8. **Draft the boundaries.**
   - Source has clarifying text → adapt it → `boundary_provenance: source`.
   - A close CSTA analog exists → adapt its boundary language to the state statement's scope → `drafted`.
   - Neither → write narrow includes and explicit excludes from the statement alone → `drafted`.
   - The cognitive verb is the spine of every boundary. An "evaluate" standard must exclude mere exposure. A "create" standard must require student production.
   - Write `boundary_excludes` even when it feels obvious. Every validated false-positive catch we have came from an explicit exclusion.
   - When the state's intent is unclear, say so inside the boundary text. Do not guess broad in silence.
9. **Draft the keywords.** These are retrieval terms. They are never sufficient evidence.
10. **Validate with a script, not by eye.** Check required fields, unique ids, count equals array length, non-empty `boundary_includes` and `keywords`, provenance present, identity trio present.
11. **Name and emit the file.** `FRAMEWORK_SET_YEAR.json`. Example: `NC_CS10_2025-26.json`. When `standard_set` is only the vintage, use `FRAMEWORK_YEAR.json`. The canonical home is the `ingested_json/` folder.
12. **Emit the review sheet.** Columns: `id, statement, nearest_csta, boundary_provenance, boundary_includes, boundary_excludes, reviewer_verdict, reviewer_edit`. The last two stay blank for the human reviewer.

### The quality bar

- Verbatim statements. Any paraphrase is a defect.
- Extraction count reconciled against the source.
- Every drafted boundary traceable to source text or to a cited analog.
- **Conservative by default.** A narrow boundary makes a false negative that the reviewer finds. A wide boundary makes a silent false positive. Prefer the recoverable error.

### What we have ingested

**Completed work, recorded as examples. No tool reads this table.**

| Set | File | Count | Notes |
|---|---|---|---|
| Oklahoma CS | `OK_standards.json` | 55 (L1 28 for grades 9–10; L2 27 for grades 11–12) | Five CSTA-2017-era concepts. All 55 boundaries hand-drafted; the source has no clarification text. `framework_year` 2018. Two OCR artifacts in source ids preserved verbatim and flagged in `schema_notes`: `LI.CS.T.01` and `Li.CA.CVT.01`. |
| Texas TEKS CS I | `TX_CS1_2025.json` | 62 | Ids use the prefix form `CS1.(N)-(L)`, chosen over bare ids. Concepts populated from TEKS strand headings. |
| Texas TEKS CS II | `TX_CS2_2025.json` | 59 | CS2 expectations that extend a CS1 expectation name that relation in `boundary_excludes`, so CS1-level evidence cannot be credited against a CS2 expectation. |
| California CS 9–12 | `CA_CS-Standards_2018.json` | 30 | Statements verified verbatim against the source CSV by script. |
| California CTE ICT | `CA_CTE-ICT_2013.json` | 322 rows; 277 atomic children | Identity trio `CA · CTE-ICT · standards`, confirmed not to collide with the existing `CA-CS` set. |
| CSTA 2026 | bundled reference | 196 foundational, 135 specialty | Ships its own boundaries. Used as the drafting reference, never as a crosswalk target. |

**Rules found during these runs.**

- The TEKS §(c)(5) boundary rule: "including" means mandatory content; "such as" means illustrative. Apply it systematically.
- Two legacy defects were found and corrected in an inherited TX CS I file: one missing standard, and two standards carrying network statements from a different framework.
- Source CSV parsing often needs `encoding='utf-8-sig'` to strip the byte-order mark.
- Read large standards JSON once into a dict keyed by id. Do not re-read the file for each standard.
- Filter to the target grade band before evaluation. On one run this reduced 196 foundational standards to 46 candidates.

---

## 3. Mapping to a course

The skill is `csta-alignment`. It runs **forward alignment**: given this curriculum, which standards does it address, at what level, with what evidence?

### Procedure

1. **Get the curriculum from the corpus.** Read `manifest.csv` first. For each lesson, read both records: the lesson plan (`lessons/<unit>/NN-<slug>.json`) and the student instructions (`levels/<unit>/NN-<slug>.levels.json`). Both asset types are now present, so the old undercount caveat no longer applies. Record `script_name` and `stable_id`, never a unit number or a lesson title.
2. **Set scope. Do not ask scope questions.** The default is forward, all domains, every grade band in the standards file. Honor a narrower scope only if the user states one. A Programming unit will show most Society standards as not addressed. That is a scope mismatch, not a curriculum shortcoming. Report it plainly.
3. **Load the standards file.** Validate the required fields. Read the identity trio for the report header and the CSV columns. If `boundary_provenance` is `drafted`, say so in the report: a rejection may be the boundary's fault, not the curriculum's.
4. **Rate each standard** with one of four levels.
   - **Not addressed** — no meaningful presence.
   - **Introduced** — exposure only. A mention, a definition, a brief example. Students produce no evidence.
   - **Developed** — students work with the concept across activities, with practice and feedback, but with no summative assessment.
   - **Mastered** — students produce observable evidence at the cognitive level the standard demands, with feedback and revision.
5. **Point to the evidence.** Name the activity, prompt, or task. "The lesson is about this topic" is not evidence. A word match is not evidence.
6. **Cap optional pathways at Introduced.** If the evidence sits only in a student-choice branch, name the branch in the note.
7. **Run the verification pass. It is mandatory.** Re-check every claimed pair as if it were someone else's work:
   1. **Boundary check** — does the evidence match an exclusion, or does the inclusion need an element the curriculum lacks?
   2. **Evidence check** — can you point to a specific task?
   3. **Cognitive verb check** — does the student task operate at the standard's verb level? If not, demote.
   4. **Artifact-type check** — the standard names a program, dataset, or documentation; the curriculum gives a prompt or a poster. Reject, or keep with a stated caveat. Never claim it in silence.
   5. **Overclaim scan** — re-examine any lesson mapped to 6 or more standards, and any Mastered rating built on one activity.
   6. **Evidence-overlap annotation** — when one piece of student work evidences standards in two concept areas, keep both claims and annotate both notes. Many-to-many mapping is how crosscutting standards work.
   7. **Count check** — verify by script that Mastered + Developed + Introduced + Not addressed + Boundary issues equals the candidate-set size, and that the summary table matches the report body and the CSV.
8. **Write the report and the CSV.** Report sections: Summary, Standards addressed (by level, with evidence), Standards not addressed, Boundary issues.

### Rules the corpus adds

- **Read the sublevels.** A parent `bubble_choice` or `level_group` level holds no text of its own. Sixty percent of the student words sit in children. An extraction that reads parents only completes without error and undercounts in silence.
- **Check the authored standard references first.** The curriculum already carries 1,255 standard references, all resolved to statement text: CSTA 2026 (424), CSTA 2017 (789), AI4K12 2021 (42). These are the authors' own claims. They are a strong prior and a useful cross-check. They are not evidence on their own, and they can be wrong in both directions — see the under-claim case in section 9 of the handover, summarised below.
- **The capstone is one lesson, not ten.** Do not invent lesson numbers inside it. Until a level below the lesson exists, a claim against a capstone milestone joins at the lesson level and carries a note.
- **A choice-level claim is met by a fraction of the class.** Cap it at Introduced and name the option.
- **Five project lessons have no authored objective.** There is nothing to anchor a forward claim on. Say so rather than inferring one.

### The authorship question

In AIF Semester 2, unit `ai-and-algorithmic-decisions-2026`, Lesson 5, the stated objective is to write if/else statements to control app behaviour. No student is ever told to write a conditional. In all four options the student draws a flowchart, asks the AI to write the code, then checks the code against the flowchart.

Three facts bear on this.

1. **CSTA 2026 treats these as different skills.** `HS-PRO-RD-18` covers evaluating AI-generated code for accuracy, reliability, and alignment with requirements. The framework does not accept prompting as a way of writing. It gives evaluation its own standard.
2. **The authors already use that standard.** `HS-PRO-RD-18` is claimed on 29 AIF and AID lessons, including five others in this same unit. It is not claimed on Lesson 5, which is a clear case of it. Lesson 5 appears under-claimed.
3. **The curriculum distinguishes the two models on purpose.** Across all 24 units, students are told to write or edit code 622 times, and to ask the AI to write code 235 times. Programming units are almost entirely student-written. AI units are mixed.

**The tool must not judge this.** It records the fact. The mapping applies a policy, through a new field with values such as `student authored`, `student directed, AI produced, student verified`, and `AI produced, not verified`. Then "does prompting count" is one written decision per framework, not an implicit judgement made 315 times. For a silent framework, record your reading and your reasoning. For CSTA 2026, the framework has already decided.

### The five failures to avoid

- Vocabulary-only matching. "Sorting socks" does not address a data-sorting standard.
- Overclaiming on a single mention.
- Ignoring the cognitive verb.
- Mapping one lesson to too many standards. One to three is normal and correct.
- Reverse-claiming. Do not claim what the curriculum *could* cover.

### Reconciling against an existing mapping

Run the forward evaluation independently first. Then diff. For pairs that exist only in the prior mapping, apply the verification checks. Accept the defensible ones and tag the note `added on reconciliation`. Reject boundary violations and evidence-free topical guesses. Deliver the reconciled CSV **and** a rejection log with a specific reason for each rejection.

### What we have aligned

**Completed work, recorded as examples. No tool reads this table.**

| Run | Result |
|---|---|
| AIF S2 U4 "Iterating with AI" to CSTA 2026 | Compared against a prior human mapping. 13 standards shared; 3 in the prior mapping only (`HS-PRO-PD-13`, `HS-PRO-PD-15`, `HS-DAT-DI-25`); 9 in ours only, of which 5 sat in SOC/SYS, which the prior mapping excluded entirely. |
| AIF to Texas CS I | 79% coverage. 49 of 62: 19 Mastered, 21 Developed, 9 Introduced, 4 boundary issues, 9 not addressed. |
| AIF to Texas CS II | 42% coverage. 25 of 59: 6 Mastered, 12 Developed, 7 Introduced, 8 boundary issues, 26 not addressed. |
| AIF to California CS 9–12 | 26 of 30 addressed; 20 at Developed or above. |
| AIF to California CTE ICT | `AIF_CA_CTE-ICT_2013_mapping.csv`. 307 claim rows across 122 distinct standards. Five per-group reports. Boundary review gated to about 197 rows. |

**Two lessons from those runs, both worth repeating to a district.**

- **Explain thin coverage structurally, not defensively.** Texas CS II is close to AP CS A. AIF does not teach class authoring, inheritance, recursion, big-O, named sorting algorithms, or hexadecimal and octal. Absence was confirmed by search across all 12 units, not asserted. 12 of the boundary rejections would convert to coverage if a Texas reviewer widened the drafted boundaries.
- **An honest near-zero is a useful result.** The CTE Games and Simulation pathway returned two Introduced, ten boundary rejections, and nothing higher. The boundary work is documented so that game-themed coding exercises cannot inflate the result by keyword match. That result tells a CTE director not to propose AIF against that pathway.

A cross-cutting difference from the earlier human mappings: the prior work tagged standards to lessons **by topic**. This pipeline tags them **by the cognitive verb and by where the student performs the activity**. That single difference explains most lesson-level placement disagreements.

---

## 4. Storing the mapping in our schema

Two files define the contract. Read `STANDARDS_SCHEMA.md` before you emit anything.

### The standards file

One JSON file for each standards set.

Top level: `source`, `scope`, `standard_count`, `framework`, `standard_set`, `set_type`, `framework_year`, `schema_notes`, `standards`.

Consumers must ignore unknown top-level fields. When the identity fields are absent, default to `framework` = `CSTA`, `framework_year` = `2026`, `set_type` = `standards`, `standard_set` = the vintage.

**Per-standard fields:**

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Unique in the file. The source's own identifier, verbatim. Never invented, never normalized. |
| `statement` | yes | Verbatim. |
| `grade_band` | yes* | Or `level` for specialty-style sets. At least one must be present. |
| `level` | no | Specialty course band, `S1` / `S2`. **Do not overload this field to carry the course.** Course identity lives in `standard_set`. |
| `concept` | yes | The source's own top-level category. Must be consistent inside a file; it drives scope filtering. |
| `subconcept` | no | |
| `boundary_includes` | yes | What counts. Usually drafted for state sets. |
| `boundary_excludes` | strongly recommended | What does not count. This is the primary false-positive defense. |
| `keywords` | yes | Retrieval terms only. |
| `boundary_provenance` | yes for ingested sets | `source`, `drafted`, or `drafted+reviewed`. |
| `nearest_csta` | no | Ingested sets only. A drafting aid and audit trail. |
| `practices`, `dispositions`, `ai_related`, `implementation_examples`, `interdisciplinary_connections` | no | `implementation_examples` is worth drafting; it calibrates the Introduced / Developed / Mastered call. |

**Provenance is the rule that makes state ingestion safe.**

1. Every ingested standard carries `boundary_provenance`.
2. A drafted boundary is adapted from a cited analog, or written conservatively when no analog exists.
3. Human review is a one-time gate for each standards set. After review, re-mark the file `drafted+reviewed`.
4. When the engine rejects a pair purely on an unreviewed boundary, the log must say so.

### The mapping CSV

One row for each (standard, lesson) pair. A standard evidenced in three lessons gets three rows.

```
year, state, standard_set, set_type, standard_id, course, semester, unit, lesson, mastery, evidence, note
```

Field rules that are easy to get wrong:

- `state` holds the `framework`, not a US state name. `CSTA` is a valid value.
- `standard_set` is what keeps an AIF-to-NC-CS10 mapping distinct from an AIF-to-NC-CS-Standards mapping. Never drop this column.
- `semester` is a separate column. Never fuse it into `unit`.
- `unit` is the number alone. Write `6`, not `S1-U6`.
- `lesson` is a bare token. Strip any `L` prefix, so a viewer can render a `unit.lesson` pill. Non-numeric lessons such as `Capstone` are allowed and must sort after numeric ones.
- `mastery` is the **aggregate** rating across the unit or course, repeated on every contributing row. It is not a claim that the single lesson reaches that level alone.
- `evidence` is a short pointer for fast human spot-checking.
- `note` carries caveats: `inference`, boundary caveats, optional-pathway caps, `added on reconciliation`.

File name: `COURSE_FRAMEWORK_SET_YEAR_mapping.csv`. Example: `AIF_NC_CS10_2025-26_mapping.csv`. One file for each course × standards set, with both semesters inside. The canonical home is the `mapped_standards/` folder.

**The `All_*` aggregate files that a viewer or server reads are generated by concatenating the per-mapping CSVs. Never edit them by hand.**

### Schema extensions added during the CA CTE run

These came from a hierarchical source and should be treated as part of the contract now.

- `hierarchy_role` and `rating_rule` on every standard. Umbrella `X.0` rows are rated by rollup from their children, never independently. Without this, coverage percentages double-count.
- `source_metadata.addressability`, with values `curriculum` and `program`. Some CTE standards are program or experience requirements that no curriculum can satisfy.
- A fourth reporting bucket, **not curriculum-addressable**, which separates program requirements from genuine content gaps.

### The catalog CSV

A flat lookup shape derived from the canonical JSON by field mapping.

```
state, standard_set, set_type, identifier, standard, concept, grade, framework_year
```

Used for `CA_CTE-ICT_2013_catalog.csv`, 322 rows. Every mapped code in the California file existed in the catalog, so that ingestion is clean. Codes ending in `.0` are parent headings, not assessable standards. There are 45 of them in 322 entries, so 277 standards are countable.

### The join columns (added by `join_mapping.py`)

A mapping row names a lesson by course, unit, and number. Those three are not durable: units are renumbered, lessons are renamed, and keys go stale. `join_mapping.py` adds durable identity without changing the original columns.

```
curriculum_version, script_name, lesson_stable_id, lesson_name,
lesson_content_hash, join_status, join_note,
status, reviewed_by, reviewed_on
```

**`lesson_content_hash` is the one that matters.** When the corpus is rebuilt, any row whose lesson hash changed is a row to re-check. This is the whole answer to the stale-spreadsheet problem, and it is the field the internal tool's re-run diff reads.

Join test result on the California CTE mapping: 214 rows, 207 matched a lesson exactly, 7 matched at a coarser level because they pointed inside the capstone.

**Reconcile this count before you rely on it.** Earlier session records describe a CA CTE mapping of 307 claim rows across 122 distinct standards, run across all five pathway groups. The handover describes 214 rows across 76 standards, in scope C plus KPAS. The most likely reading is that these are two artifacts — the full run and the in-scope subset — but confirm which file is canonical before either number goes in front of a state.

### The coverage report (`coverage_report.py`)

The mapping records matches only. It holds no row for a standard the course misses, so it cannot answer "what percentage do you cover", which is the question states ask. Indiana, for example, required 85 percent.

`coverage_report.py` writes one row for every standard in the catalog, including the misses. The California result:

| Part of framework | Standards | Covered | Percent |
|---|---|---|---|
| C — Software and Systems Development | 61 | 35 | 57% |
| KPAS — Anchor Standards | 88 | 41 | 47% |
| **In scope (C + KPAS)** | **149** | **76** | **51%** |
| A — Information Support | 40 | 0 | — |
| B — Networking | 39 | 0 | — |
| D — Games and Simulation | 49 | 0 | — |

**Scope is a judgement, not a fact.** Against the whole framework, coverage is 27 percent. Against C plus KPAS, 51 percent. Both are true. C plus KPAS was chosen because AIF is a software course and A, B, and D are different careers. **Scope is therefore an explicit column in the output, and every standard has a row, so anyone can change the scope and recalculate.** Never publish a coverage percentage without its scope beside it.

Two results to carry forward:

- 73 in-scope standards are not addressed, and they cluster. The largest cluster is 11 health and safety standards, one of which requires Material Safety Data Sheet instructions. An AI course will never meet these and should not try. Other gaps, such as the 5 database standards, are real and could be closed.
- 41 of the 76 covered standards carry a boundary note. They are covered in part, not in full. If a state counts only complete coverage, the number is closer to 35 than to 76. **Decide which number you are quoting before a state asks.**

### The authorship field (to add)

Add one field to the mapping to record who wrote the code, with values such as `student authored`, `student directed, AI produced, student verified`, and `AI produced, not verified`. See the authorship question in section 3. Without this field, the prompting judgement is made implicitly, lesson by lesson, 315 times.

### The unsolved schema problem: multiple vintages

When a state re-adopts its standards, three failures appear:

1. **Silent id collision** across vintages.
2. **Convention mismatch** that produces false confidence in a viewer.
3. **No successor link**, so nobody can tell which old record the new one replaces.

The proposal on record is a `supersedes` / `superseded_by` pair, plus a diff-and-carry-forward workflow. This is not built. Settle it before the store holds two vintages of one framework.

---

## 5. Internal tool — Standards and Course Objective Mapper (#3a)

This is the **producer**. It creates alignment records. Audience: our own staff — alignment contractors, the curriculum team, and RPs. Districts never see it.

### Problem statement

Contractors do our alignment work by hand, one document at a time. The results go into spreadsheets and Google Docs that nobody can search. Each new request costs money, so we fund AIF and AID only, and we say no to CSF and CSD requests. Older work is out of date, or sits in another format because another team or an RP produced it. When we update a course, we cannot tell which alignments are now wrong. Demand is diversifying: state CS standards, ISTE, CTE, industry lists, and one-off district objective sets.

### Hypothesis

Alignment is a repeatable process, not new research each time. One format for every standards set drops the cost of each new request far enough that we can say yes. It also makes a re-run after a curriculum update routine maintenance instead of a new contract.

### Product description

The tool does two jobs over one data contract.

First, it reads a set of standards and puts it into our format. Standards documents rarely say how much teaching is enough. The tool writes a first draft of those notes. A person checks the draft one time for that set.

Second, the tool compares selected courses to the standards. It shows which standards each course teaches, how deeply, and which lesson gives the proof. It also shows the close matches that are not real matches.

**The tool must be a web service, not a chat skill.** Three reasons:

1. Contractors and RPs must run it without Claude Code.
2. Records must persist and must be keyed to the curriculum version. A stateless skill can produce a report. It cannot tell you which records went stale.
3. It is the write side of the external tool.

The existing skill logic becomes the engine inside the service. It is not thrown away.

### Infrastructure

- Standards files in our format, with vintage and boundary provenance.
- **The curriculum corpus**, holding lesson plans and student instructions, rebuilt from the repository. See section 1.
- **`curriculum_version` and per-lesson `content_hash`.** These exist now. They are what make a record store possible, and what turn "which alignments went stale" from a guess into a diff.
- A record store keyed on (standards version, `lesson_stable_id`, `lesson_content_hash`).
- The corpus `out/` directory kept in its own git repository, committed after every extraction run. `git diff` is the change report. **Do not build a monitor.**

**User inputs:** a standards document, or a selection from the sets we hold; the courses and units to check; the grade bands to check; a reviewer's verdict on each drafted boundary.

**Outputs:** an alignment report with evidence for each pair; a machine-readable record set; a boundary review sheet; provenance and confidence flags; a re-run diff that shows what a curriculum update changed.

### User journey

1. A district asks about their state standards.
2. A contractor adds the standards document. The tool characterizes it and asks for scope confirmation.
3. The tool emits the standards file and the boundary review sheet.
4. A person checks the drafted notes one time. The set is marked reviewed.
5. The contractor picks the courses and runs the alignment.
6. The verification pass flags overclaims, artifact mismatches, and boundary rejections for the person to resolve.
7. Approved records publish to the store. The external tool can now show them.
8. After a curriculum change, the affected records are flagged and run again.

### The review screen

A mockup exists, in CodeAI brand styling, with no hero section. The design decisions behind it:

- **The screen is a queue, not a table.** The external tool displays finished results, so a sortable table is right there. This tool needs a person's judgment on what the engine proposed, so the unit of the interface is one standard at a time, with the proof visible and Accept or Reject beside it. Counts at the top show progress through the queue.
- **Two flag types, in plain language.** "Lesson may not go deep enough" and "Close match, likely not a real one". These are the two ways an automated match usually goes wrong. Surfacing them keeps the reviewer's attention on the 12 that need thought instead of re-reading all 46.
- **The lock banner is the release gate.** Results built on unchecked notes cannot reach the public tool. The publish action stays blocked, with the reason stated on screen. This part of the mockup argues for a policy, not only a screen.
- **"Compare to last run"** answers the stale-spreadsheet problem. The course version is stamped in the header, so a re-run can show what changed.
- **An internal marker.** A person must be able to tell at a glance that this is not the public site.

Two questions the mockup left open:

1. Can the reviewer change the level in a dropdown, or only accept and reject what the tool proposed?
2. Is a queue of one-at-a-time cards right for a contractor working through 46 standards, or would a dense table with only the flagged rows opened be faster?

---

## 6. External tool — Standards and Course Objective Lookup (#3b)

This is the **consumer**. It displays approved records. It computes nothing.

### Problem statement

Our website does not show which standards our courses teach, at scale. What exists is a spreadsheet that is hard to read, hard to navigate, and impossible to link to. Districts compare our courses to their own standards by hand. Sales has nothing to show for the most common procurement question. Every question becomes a promise to reply later.

### Hypothesis

Districts do not want the full table. They want one answer: does this course teach what we must teach? One screen answers that. It replaces the spreadsheet and the follow-up email.

### Product description

A public web page over approved records. A district picks a standards set and a course, and sees the coverage level for each standard with the lesson evidence behind it. A district can also start from one standard and see which courses teach it. The page exports to a PDF for a board packet. Each view has a permanent link, so an RP can send a district straight to it.

**Release gate:** the page shows only records whose boundaries a person has checked. Publishing alignment that rests on unreviewed drafted boundaries is a credibility risk. This gate is the main dependency between the two tools.

### Infrastructure

- The record store produced by the internal tool. This product creates no alignment data of its own.
- Course and unit metadata: grade band, sequence, current version.
- A registry of standards sets with the vintage of each, so a district can tell which version of their standards they are reading.

**User inputs:** the state or standards set; a course, grade band, or single standard; the direction of the question.

**Outputs:** a coverage table with level and evidence; an honest display of what is not addressed; a branded PDF; a shareable link; an engagement signal for the CRM.

### Audience

District curriculum leaders, CTE directors, and state agency staff evaluating adoption. RPs and growth managers use it in sales conversations.

### User journey

1. A district leader opens the page from our website or from a partner's link.
2. They pick their state and a course.
3. They see which standards the course teaches, and how deeply.
4. They open one standard to see the lesson that teaches it.
5. They save a PDF, and may give an email address.
6. The partner sees the visit and follows up with real context.

### Prior art: the Standards Map Viewer

An embedded district-facing viewer already exists and was migrated onto the CodeAI design system. What that work established:

- The data-loading, CSV and PDF export, sorting, filtering, and embed-mode logic were not touched. Only presentation changed.
- Brand fonts (Space Grotesk for headlines and identifiers, Geist for body and UI) are bundled locally with `@font-face`, not pulled from a CDN. School networks filter CDNs.
- Unit category badges were remapped from off-brand solid fills with white text to brand-family light tints with dark ink. This fixed contrast failures present in the original.
- No logo is placed on the page, because the embedding site carries its own.

Treat this viewer as the starting point for #3b, not as a competing build.

---

## Decisions already made

1. **The internal alignment data and the external tool are the same asset.** Expose it, and districts self-serve the crosswalk they now ask us to produce.
2. **The internal tool runs as a web service.** Version-keyed records are the reason.
3. **Boundary review is a release gate, not a technical detail.** Internal experiments may run on drafted boundaries. District-facing output may not.
4. **The Standards work split into a producer (#3a) and a consumer (#3b).** They are separable builds with different audiences and very different risk.
5. **The Pathway Builder is a separate product.** The Standards products answer "does this course teach what we must teach?" The Pathway Builder answers "which courses should we teach, and in what order?"
6. **The District Implementation Portal and the CRM sync are pre-sprint infrastructure, not sprint candidates.** A sub-team could otherwise spend three days on scaffolding with nothing on top of it.
7. **The tagged asset inventory is the highest-leverage pre-sprint task.** It unblocks the Recommendation Engine, the Standards work, and the Resource Generator at once — but only if it is scoped once, against a shared schema.
8. **The curriculum is locked.** Alignment reports observe. They do not recommend curriculum changes.
9. **Write all briefs in Simplified Technical English.** An earlier technical draft proved too jargon-heavy for cross-functional sprint execution. Keep the technical version for the build team; the plain version is for everyone else.
10. **The extracted corpus replaces the PDF and the snapshot pack as the evidence base for alignment.** Source: the `code-dot-org` repository, `staging` branch.
11. **The curriculum snapshot pack stays, for slides and PL design.** A small, readable, curated corpus is the right shape for deck building and PL experience design. It is the wrong shape for alignment. Do not let the two uses converge.
12. **Change detection is `git diff` plus `content_hash`. We do not build a monitor.** The repository is already a versioned record.
13. **Record `script_name` and `stable_id`. Never record a unit number or a lesson title as an identifier.** Unit numbers are inconsistent within AIF S2, and lesson keys do not follow renames.
14. **No state is built into any tool.** Every state named in this document is finished work, kept as an example.
15. **CSTA 2026 is the anchor, on purpose.** It is the reference for drafting boundaries and the default standards set. It is not a required participant in a run.

---

## Open questions

Items 1, 2, and 3 come before the sprint. The rest can wait. The question "where does curriculum data come from" is now answered — see section 1.

1. **Check AID Unit 1 against the older alignment documents.** Eight lessons carry stale titles and two changed position. Any prior alignment that referred to those lessons by title or number is probably mismapped. AID Unit 1 is a current priority for state alignment updates. Small effort, real risk, do it first.
2. **Does the record schema get settled on day one?** The external tool is a thin build on the internal tool's data and is nearly worthless without it. A defensible alternative: build the external tool against a hand-curated slice of existing AIF or AID records, and prove district value before the full internal pipeline exists.
3. **Do we show gaps in public?** The external tool is more credible with "not addressed" visible, and less comfortable for sales. If we hide the gaps, the tool becomes marketing — which is what the spreadsheet already failed at. Decide deliberately. Do not discover this in review.
4. **Make the identity trio required, and fail loudly when it is missing.** Today a file without it silently becomes a CSTA 2026 file. See *Rules, examples, and the anchor*.
5. **How do we hold two vintages of one framework?** See the `supersedes` proposal above.
6. **Can the reviewer edit a level, or only accept and reject?**
7. **Queue of cards, or dense table with flagged rows opened?**
8. **For the CA CTE catalog:** confirm `framework_year: 2013` against the current ICT sector document; decide whether umbrella rows are excluded from any catalog-driven count; decide whether `concept` should carry the cluster-level subconcept instead of the group name for a browse interface.
9. **Which curricula do we support beyond AIF and AID?** CSF and CSD requests are the ones we now decline. The cost argument for the internal tool rests on saying yes to them. Extending the corpus is a command-line flag, not new code.
10. **Which CA CTE mapping file is canonical?** 214 rows against 76 standards, or 307 rows against 122. See section 4.
11. **Run the distiller across all 315 lessons.** This shows where the "Do This" pattern holds and where it does not. It is the test of whether the distilled layer is worth keeping.
12. **Add a level below the lesson.** Needed for the capstone and other long lessons. The milestone names are already in the corpus.
13. **Add the authorship field to the mapping.** See section 3.
14. **Fold the coverage rows into the mapping**, so there is one file and not two.
15. **Collect worksheets and slides — last.** 133 of the linked documents are answer keys restricted to verified teachers. Settle who may see the corpus before it holds that content.

---

## Where things live

| Thing | Location |
|---|---|
| Ingestion skill | `/mnt/skills/user/standards-ingestion/` — `SKILL.md`, `STANDARDS_SCHEMA.md`, CSTA reference JSON |
| Alignment skill | `/mnt/skills/user/csta-alignment/` — `SKILL.md`, `STANDARDS_SCHEMA.md`, CSTA foundational and specialty JSON |
| Curriculum source | `code-dot-org` repository, `staging` branch. Sparse-clone `dashboard/config/` paths: `courses`, `scripts_json`, `course_offerings`, `standards`, `levels`, `scripts` |
| Extracted corpus | `out/` — `manifest.csv`, `manifest.json`, `warnings.json`, `levels_manifest.csv`, `levels_warnings.json`, `lessons/`, `levels/`, `distilled/`. Keep it in its own git repository. |
| Extraction and mapping tools | `extract_curriculum.py`, `extract_levels.py`, `distil_lesson.py`, `join_mapping.py`, `coverage_report.py` |
| Curriculum snapshot pack | `/mnt/skills/user/codeai-curriculum/` — `SKILL.md`, `manifest.json`, `aif/s1/`, `aif/s2/`. **For slides and PL design. Not for alignment.** |
| Ingested standards files | `ingested_json/`, one file for each set, named `FRAMEWORK_SET_YEAR.json` |
| Mapping CSVs | `mapped_standards/`, named `COURSE_FRAMEWORK_SET_YEAR_mapping.csv` |
| Aggregate files | `All_*`, generated by concatenation, never hand-edited |
| Sprint repo | `codeai-az` (private). A separate scaffold repo holds the portal index and one page for each candidate tool. |

**A note on the sprint team.** About half the team is new to git and to code. Claude Code is the interface. Nobody needs to learn branching for this. The standard is Git for Windows plus the GitHub CLI, with branch protection and pull-request merges as the safety net. `CLAUDE.md` in each repo carries the conventions and the student-data hygiene rules.
