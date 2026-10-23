# Prospective content measurement plan

## Decision and pilot

Test whether a regular publishing schedule can produce useful reach and measured destination traffic, and whether comparable carousel or Reel treatments warrant a larger test. Current lifetime-format medians are too age-confounded to choose a winner. The sharp reduction in retained feed publications motivates testing a renewed schedule; it does not prove that posting less caused the engagement decline.

Run an initial **eight-week measurement pilot**, with two matched band-authored posts per week (16 posts, eight matched blocks). This is a feasibility and variance pilot, not a powered guarantee of detecting a marketing effect. Set the start date and schedule before collection; no task or publication has been scheduled by this analysis.

## Assignment and outcomes

- In each weekly block, use the same recording and call to action in two matched creative treatments: one carousel, one Reel. Randomly assign their order to two prespecified slots. Balance the selected songs across blocks; include Funny Guy and one growing catalog recording, using stable song IDs.
- Keep planned budget equal within a block; if there is no paid promotion, record an explicit zero. Log any unplanned paid exposure, release, show, playlist placement or collaboration. Shared followers and carryover between posts can still create interference; do not treat audience exposures as independent participants.
- **Primary outcome:** per-post reach after exactly seven 24-hour intervals from publication. Report the within-block difference and the difference in `log(1 + reach)`, with both underlying levels. Never sum this into unique people across posts.
- **Secondary outcomes:** same-age views; engagement actions (likes + comments + shares + saves); actions divided by that post's reach when reach is positive; unique tagged destination link clicks under the link provider's documented definition. Treat secondary comparisons as exploratory and retain null/weak results.
- Record Spotify daily streams for the linked recording as context, with the existing UTC/Pacific mismatch documented. Do not call resulting aggregate changes attributed listening. A stronger causal streaming test needs an attribution mechanism or defensible experimental unit and control that this pilot does not provide.

## Required record

For every post capture block ID, assignment/order, stable platform/post/account IDs, publication timestamp and timezone, format, creative/topic label, Spotify recording ID, destination URL/tag, planned and actual paid spend, event flags, retrieval timestamp, exact outcome age, metric definition/scope, raw value, precision and value status. Save native exports/screenshots at 24 hours and 7×24 hours; retain the raw evidence and checksum. Record the delay if a capture misses its target age; do not silently mix ages.

Predefine handling: retain zero outcomes, distinguish missing captures from zero, log deletions and technical failures, and show results both with all assigned posts and any documented invalid-capture exclusions. No post is excluded solely for performing poorly. Do not stop early because one format appears ahead.

## Review after the pilot

Review completeness, treatment balance, budget deviations, block-to-block variation and the distribution of paired outcomes. Eight blocks provide limited independent information; do not use 16 posts, their viewers or repeated snapshots to inflate the sample. Show all paired outcomes and whether the direction repeats across weeks and songs. If formal randomization inference is used, its exchangeability and interference assumptions must be assessed first; otherwise report the pilot descriptively.

Choose a practically worthwhile reach/click improvement and use the pilot's observed variability to size the next study. Predeclare that next study's primary comparison, stopping rule and uncertainty method before seeing its outcomes. A sustained schedule may be operationally useful even when the format comparison is inconclusive.
