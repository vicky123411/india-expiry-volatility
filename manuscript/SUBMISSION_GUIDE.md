# How to submit the paper (easy guide)

## 1. Which journal
**First choice: *Journal of Emerging Market Finance* (Sage).**
- Indexed in Scopus.
- **No fee** to submit or publish.
- Covers emerging financial markets with practical value, which is exactly this paper's topic.
- Rules: at most 8,000 words in total, counting tables and references (ours is 7,105; the title page states it); an abstract of about 100 words; 4–6 keywords; JEL codes; APA references; anonymous review.
- Submit at the journal's Sage page: https://journals.sagepub.com/author-instructions/emf

**If rejected, try next (same files work, small changes only):**
- ***IIMB Management Review*** (Elsevier, Scopus). It is open access, but IIM Bangalore pays the publication fee for authors. Upload `highlights.docx` there, because Elsevier asks for highlights.
- ***Vikalpa*** (Sage, IIM Ahmedabad, Scopus). No fee. Its research articles also have an 8,000-word limit.

**Be realistic:**
- No journal guarantees acceptance.
- Reviewers usually ask for changes ("revise and resubmit"). That is normal, so plan for one round of revisions.
- Never pay a journal that promises fast or guaranteed acceptance. These are often predatory journals, even if they claim to be "Scopus indexed".

## 2. Files to upload (in `out/`)
| File | What it is | Upload as |
|---|---|---|
| `manuscript.docx` | The paper with **no author names** (needed for anonymous review) | Main document |
| `title_page.docx` | Your name, university, email, declarations, word count | Title page |
| `supplementary_material.docx` | Extra tables and figures | Supplementary file |
| `cover_letter.docx` | Letter to the editor | Cover letter |
| `highlights.docx` | 5 one-line findings (only for Elsevier journals) | Highlights |
| `*.pdf` | The same files as PDF, for checking | Keep for yourself |

## 3. Before you click submit (checklist)
- [ ] **Read the whole manuscript once.** You must be able to explain every table. The `STUDY_GUIDE.md` in the main folder explains everything simply.
- [ ] **Title page:** add your ORCID iD. Get one free at orcid.org.
- [ ] **Title page:** check the "Use of artificial intelligence tools" sentence. Sage requires you to say if AI helped, and AI cannot be an author. Keep the sentence true.
- [ ] **Title page:** fill in or delete the Acknowledgements line.
- [ ] **Supervisor:** if a professor helped or will check the paper, consider asking them. A senior co-author makes acceptance more likely; add them only if they really contribute.
- [ ] **Cover letter:** change the date if you submit on another day.
- [ ] **Anonymous review:** do not put your name, university or GitHub link inside `manuscript.docx` (it is already clean).
- [ ] **Sage account:** create one, then fill in the online form: title, abstract, keywords, author details.

## 4. If you change anything later
- **Re-run the analysis:** run `python scripts/run_all.py`, then `python scripts/descriptives.py`, then `python scripts/extra_checks.py`.
- **Rebuild the paper:** run `python manuscript/build.py`. All tables in the paper are rebuilt from the result files automatically, so you never retype numbers.
