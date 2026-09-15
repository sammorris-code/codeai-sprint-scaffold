# Building the review queue

A guide for the person building the main screen of the Standards Mapper.

**You do not need to write code.** Claude Code writes it. Your job is to say what
the screen must do, look hard at what comes back, and send it back when it is
wrong. That is the harder half of the work and it is the half only a person can
do.

Read this once before you start. Keep it open while you work.

---

## 1. What you are building

Somewhere in a state education office, somebody has a list of things every school
must teach. We have courses. A district wants to know: does your course teach
what we are required to teach?

Answering that by hand is slow, so a tool now proposes the matches. It reads a
lesson, reads a standard, and says "I think this lesson teaches this."

**It is often wrong.** So a person checks every proposal before anybody sees it.

Your screen is where that person works.

### Why a queue and not a spreadsheet

The obvious thing to build is a big table. Resist it.

A table is right for reading finished results, and the public site will have one.
But this screen is for judging, and judging is one thing at a time. The reviewer
needs the standard, the proof, and the Accept or Reject button all in view
together. In a table, the proof is a truncated cell.

So: **one standard at a time, with its evidence beside it.**

The table on the page today is a placeholder. You are replacing it.

---

## 2. Before you start

You need the repository on your computer and a way to look at the page.

Ask Claude Code:

> Clone the codeai-sprint-scaffold repository, make me a new branch called
> `<your-name>/review-queue`, then start a local web server and tell me the
> address to open.

**You must open the page through that address, not by double-clicking the file.**
A browser will not let a page load data from a file on your desktop. The page
explains this on screen if you forget, so you will not be left guessing.

Leave the server running while you work. Refresh the page to see changes.

---

## 3. How to work with Claude Code on this

A few habits that make the difference between a good screen and a mess.

**Ask for one thing at a time.** "Build the review queue" gets you something
shapeless. The five steps in section 4 are sized to ask for one at a time.

**Look at the screen after every step.** Do not read the code. Open the page,
click things, and judge what you see. If it looks wrong, it is wrong.

**Say what is wrong in your own words.** You do not need the right technical
term. "The evidence is squashed into a tiny box and I can't read it" is a
perfectly good bug report and Claude will know what to do with it.

**Ask why when you are unsure.** "Why did you put that there?" is a fair
question. If the answer does not convince you, say so.

**Commit when something works.** Ask Claude to commit and describe what changed.
That way a bad step later can be undone without losing the good ones.

**Push back on anything that adds a setup step.** If Claude suggests installing
something, ask whether it can be done without. The answer is almost always yes,
and the moment this project needs an install, everybody on the team needs it too.

---

## 4. Build it in five steps

Each step is one request, then one look at the screen.

### Step 1 — Get the data on screen, however ugly

> Read `contract/REVIEW-QUEUE-GUIDE.md` and `contract/api.md`. Then add a file
> `tools/standards-mapper/queue.js` that loads the review queue sample data using
> the existing loader, and lists every standard on the page. Plain and unstyled
> for now. I want to see that the data arrives.

**Look for:** a list of **fourteen** standards. Count them. Eight of the fourteen
have no evidence proposed against them, and those eight must still appear. If you
count six, the screen is only drawing the ones with evidence — say so now. This is
the single most common mistake, and it is far easier to fix here than later.

### Step 2 — One standard at a time

> Now turn it into a queue. Show one standard at a time: what the standard says,
> the notes about what counts as teaching it and what does not, then the lessons
> proposed as evidence. Give me a way to move to the next one and back.

**Look for:** Can you read the whole standard without scrolling sideways? Is the
evidence given real room, or squeezed? The notes about what counts are what the
reviewer decides against — they must be visible, not hidden behind a click.

### Step 3 — Accept and reject

> Add Accept and Reject to each proposed lesson. Let the reviewer change how
> deeply the lesson covers the standard, since that is often what is wrong.
> Rejecting should ask for a short reason. Keep the decisions in the page for
> now, and add a button that downloads them as a file.

**Look for:** After you accept something, can you tell that you accepted it? Can
you change your mind? Does the progress count at the top go up?

**Say this to Claude:** "Keep everything about saving decisions in one place, so
that when we connect the real server later only that part changes." This matters
more than it sounds — see section 8.

### Step 4 — The warnings and the lock

> Show the warnings on each proposed lesson, using the exact words in the data,
> not the internal names. Then add a banner: when the standards set has not been
> checked by a person yet, the results cannot go to a district — say so plainly
> and switch off any publish action.

**Look for:** the warnings should read like sentences a person wrote — *"Lesson
may not go deep enough"* — not like codes. The banner must be hard to miss and
impossible to dismiss. It is the thing standing between a draft and a school
district.

### Step 5 — Make it work by keyboard

> Go through the whole screen and make sure every control can be reached by
> pressing Tab and used with Enter or Space, with a clear outline showing where
> you are. When the queue moves to the next standard, move the keyboard focus
> there too and announce it for a screen reader.

**Look for:** put your mouse away. Press Tab from the top of the page and work
all the way through, accepting and rejecting as you go. If you get stuck
anywhere, or lose track of where you are, it is not finished.

We build for school districts. This is part of the work, not a later pass.

---

## 5. The eleven things that must work

The sample data is not a tidy example. Every one of these has produced a wrong
claim in real work, and each is sitting in the data waiting to catch the screen
out.

**Go through this list on the finished screen, one at a time.** This is the most
useful hour you will spend on it.

1. **Eight of the fourteen standards have no evidence proposed at all.** They
   must still appear in the queue. A screen that only draws things with evidence
   will drop them silently and the totals will not add up.

   "No evidence" is not one thing, and the screen should not treat it as one.
   Of those eight: three are genuine gaps in the course, one was rejected
   because the evidence did not meet the written definition, one is a heading
   rather than a standard, one is a work-placement requirement no course could
   meet, and two were never in the running. A reviewer needs to tell those apart
   at a glance. Items 2, 3 and 4 below are three of them.
2. **Two standards were never in the running.** They belong to a different
   subject area that this course was never meant to cover. They must not read as
   a failing. Show them apart, or leave them out — but never count them as a gap.
3. **One row is a heading, not a standard.** It gets its score from the
   standards underneath it. Nobody should be able to accept or reject it on its
   own.
4. **One requirement is forty hours of supervised work experience.** No course
   can ever teach that. It is not a gap in our curriculum and must not be shown
   as one.
5. **One match has gone stale.** Somebody already accepted it, and then the
   lesson was rewritten underneath them. This is the most important thing on the
   screen. It must be obvious, and it must say that it was accepted before.
6. **One piece of evidence is optional.** Students choose between four
   activities, and only one of them covers this standard. So only part of the
   class does it. The screen must say which choice, and must never let that count
   as full coverage.
7. **One unit has no number.** Its number is simply blank. The screen must print
   the unit's name. Never "Unit" followed by nothing.
8. **One lesson is numbered "capstone".** Lesson numbers are not always numbers.
   If you sort by them, that one goes last.
9. **One lesson has no stated objective.** Say so. Do not let anything invent
   one.
10. **One lesson's internal name is its old title.** It reads "Guidelines for
    Working with AI"; the lesson is now called "Making Decisions with If and
    Else". **The screen must show the current title.** If you ever see the old
    one on screen, that is a bug — and it is exactly the bug that caused a whole
    unit to be mapped wrongly last time.
11. **The list can be empty.** Ask Claude to show you what happens when there is
    no data at all. It should say something useful, not sit there blank.

---

## 6. Rules to hold Claude to

If you notice any of these, say so. Each one has already cost somebody real time.

- **No state names or course names written into the screen.** The menus read
  whatever the system holds. If you see "Texas" or "AI Foundations" typed into a
  file, that is a bug. Adding a state should never mean editing this screen.
- **No confidence score.** The tool used to show High, Medium, Low. It was
  removed deliberately: a number invites the reviewer to trust it instead of
  looking. Named warnings replaced it. If a score reappears, push back.
- **Nothing to install.** No frameworks, no packages, no build step. Somebody
  must be able to clone this and see it work with one command.
- **Do not touch `css/layout.css` or the front page.** Everyone edits those and
  you will collide with another team. Your styling belongs in the Standards
  Mapper's own folder, and the file is already there waiting.
- **Web addresses must not start with a slash.** This sounds like trivia. It is
  not: every proposed change gets its own preview link, and an address starting
  with `/` escapes that preview and quietly loads the real site's file instead.
  The preview then shows the wrong thing rather than failing, and nobody notices.
- **Real buttons and links.** Not pictures of buttons. This is what makes the
  keyboard and screen readers work.

---

## 7. You are done when

- [ ] All eleven things in section 5 behave correctly. Checked one by one.
- [ ] The counts at the top match what is actually in the queue.
- [ ] The banner appears for the set nobody has checked, and publishing is off.
- [ ] You got from the top of the page to the last control using only Tab, and
      used every control on the way.
- [ ] Claude confirms the browser console is clean.
- [ ] An empty list shows a sensible screen.
- [ ] Claude has run `python3 contract/validate.py` and it passed.

Then:

> Commit this, push my branch, and open a pull request describing what I built.

The preview link posted on that pull request is the easiest way to show anybody
your work. It is a normal web address — you can send it to Sam.

---

## 8. What happens to this later

Worth knowing, because it affects one decision you will make.

Right now the screen reads sample data — invented standards, invented lessons.
Later it will read real data from a real database.

**Almost nothing you build will change.** The sample data was written to have the
exact same shape as the real thing, deliberately, and there is an automatic check
that fails if the two ever drift apart. When the database is ready, one small
file is pointed at it and your screen keeps working.

The one exception is **saving**. Today the reviewer's decisions live in the page
and download as a file. Later they will be sent to the server and stored. That is
a real change — which is why step 3 asks you to keep all the saving in one place.
Do that, and this is a small job later. Spread it through the screen, and it is a
painful one.

---

## 9. Two questions to bring back, not answer

These are genuinely undecided. Build something sensible, note which way you went,
and raise it.

1. **Is one card at a time actually right?** Somebody working through forty
   standards may find it slow. We think the focus is worth it. You will be the
   first person to find out. If it feels slow to you, say so — that is real
   evidence and nobody else has it.
2. **Should the screen encourage changing the depth, or mostly accept and
   reject?** If changing it is too easy, the reviewer may fiddle. If it is too
   hard, they will accept something they think is wrong. You will have a feel for
   this after an hour that nobody else has.

---

## 10. If you want the background

You do not need any of this to start.

- `tools/standards-mapper/az-sprint-standards-pipeline-briefing.md` — why this
  work exists, and what went wrong the last time we did it by hand.
- `contract/README.md` — the rules the data follows.
- `contract/api.md` — what the screen will eventually ask the server for.

And if anything here is unclear, ask. A guess in this screen becomes a wrong
claim to a school district later, which is the one outcome nobody wants.
