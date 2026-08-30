# X hiring signal: tested, not viable

**Date:** 30 August 2026
**Status:** Closed. Do not rebuild without a different data source.
**Code:** implemented in `f464205`, reverted in the following commit. Recoverable
from git history if the source problem below is ever solved.

## The idea

ResumeRadar grades a CV against the job description the user pastes in. Job
posts go stale, get recycled between companies, and are often written by
someone who is not running the interview. The people actually hiring talk in
public on X, this week.

So: a weekly job asks Grok what skills recruiters and hiring managers are
naming for each of our 15 roles on X, normalises the answer to the
`keyword_engine` vocabulary, and shows it on the role pages as live context
alongside the score.

## Why it does not work

The premise is false. Employers on X do not name tools in their posts. They
link to the job description instead.

Two trials, both using multiple pooled queries over a 7-day window, applying
the exclusions in the brief (job-board reposts, engagement bait, course and
cert adverts, self-promotion, posts naming no specific skill):

| Role | Retrieved | Excluded | **Usable** | Skills at 2+ usable posts |
|---|---|---|---|---|
| data-analyst | 102 | 101 | **1** | none |
| software-engineer | 122 | 119 | **3** | React (2) |

software-engineer is the loudest role we cover. Its single loudest query
counted 793 posts in the week and was almost entirely aggregators dumping JDs.

The decisive observation: in the software-engineer trial, **10 genuine-looking
employer, founder and hiring-manager tweets were hiring for the role and named
no tool in the post.** Ten near-misses against three usable. The problem is not
retrieval volume, filtering strictness, or the mention threshold. Real hiring
humans are findable on X; they simply do not list skills there.

Skill names *do* appear on X in bulk, inside job-board dumps, roadmap threads
and course adverts. Those are exactly what must be excluded. Counting them
would have shipped marketing volume as hiring demand, on 15 public pages, to
job seekers who cannot check it. The unfiltered 7-day query-volume counter is
attractive and wrong for the same reason.

## What we would have shipped without the trial

A weekly pipeline publishing a skills distribution derived from roughly one
usable post per role. The `--mock` fixture data claimed Kubernetes and
Terraform were rising for all 15 roles, including UX designer and Scrum
master. That was never committed.

Cost of finding out: two trial runs, about $3.50 of retrieval, no deploy.

## If this is revisited

Do not go back to X chatter. The honest source for "which skills are in demand
for this role right now" is the job descriptions themselves: aggregate keyword
frequency across many current postings per role. Countable, high-volume, and
it is the same kind of text the scanner already parses.

The parts of `f464205` worth resurrecting are source-agnostic:

- `backend/hiring_signal.py` — reader with a 14-day staleness guard, returns
  `None` on every failure so the page renders without the block
- the role-page template block and its CSS
- `data/README.md` — the checks before generated data is ever committed

Only `scripts/refresh_hiring_signal.py` is Grok-specific and genuinely dead.

## Note on the process

The bot reported the negative result straight, with real counts and an explicit
"too thin to say anything meaningful". The brief told it that empty lists are a
success case and that it must never pad or estimate. That instruction is what
made the trial informative instead of reassuring.
