---- MODULE LandingQueueMerge ----
EXTENDS LandingQueueBase


RecordCandidate ==
  /\ Mode = "merge"
  /\ run.pc = "check-pass"
  /\ entryState' = [entryState EXCEPT ![run.entry] = "awaiting-merge"]
  /\ candidate' = [candidate EXCEPT ![run.entry] = run.cand]
  /\ prHead' = [prHead EXCEPT ![run.entry] = run.cand]
  /\ checkState' = [checkState EXCEPT ![run.entry] = "absent"]
  /\ absence' = [absence EXCEPT ![run.entry] = "none"]
  /\ seenEarlier' = [seenEarlier EXCEPT ![run.entry] = FALSE]
  /\ run' = IdleRun("ready")
  /\ UNCHANGED <<leaseVars, clock, floor, entryLease, landedAs, attempt, worktree,
                 paused, secondDrain, tip, prOpen, prStored, armed, mergedAs, historyVars>>

OpenPr(e) ==
  /\ Mode = "merge"
  /\ Polling
  /\ entryState[e] = "awaiting-merge"
  /\ ~prOpen[e]
  /\ prOpen' = [prOpen EXCEPT ![e] = TRUE]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prStored, prHead,
                 checkState, armed, mergedAs, absence, seenEarlier, historyVars>>

StorePr(e) ==
  /\ Mode = "merge"
  /\ Polling
  /\ entryState[e] = "awaiting-merge"
  /\ prOpen[e]
  /\ ~prStored[e]
  /\ prStored' = [prStored EXCEPT ![e] = TRUE]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prOpen, prHead,
                 checkState, armed, mergedAs, absence, seenEarlier, historyVars>>

ChecksPost(e) ==
  /\ prOpen[e]
  /\ mergedAs[e] = NoCommit
  /\ checkState[e] = "absent"
  /\ checkState' = [checkState EXCEPT ![e] = "pending"]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prOpen, prStored,
                 prHead, armed, mergedAs, absence, seenEarlier, historyVars>>

ChecksFinish(e) ==
  /\ prOpen[e]
  /\ mergedAs[e] = NoCommit
  /\ checkState[e] = "pending"
  /\ \E r \in {"passed", "failed"} : checkState' = [checkState EXCEPT ![e] = r]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prOpen, prStored,
                 prHead, armed, mergedAs, absence, seenEarlier, historyVars>>

HeadMoves(e) ==
  /\ prOpen[e]
  /\ mergedAs[e] = NoCommit
  /\ \E c \in Commits \ Squashes :
       /\ c \notin {prHead[e], candidate[e], "c0"}
       /\ prHead' = [prHead EXCEPT ![e] = c]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prOpen, prStored,
                 checkState, armed, mergedAs, absence, seenEarlier, historyVars>>

AbsenceSeen(e) ==
  /\ Polling
  /\ entryState[e] = "awaiting-merge"
  /\ prStored[e]
  /\ prHead[e] = candidate[e]
  /\ checkState[e] = "absent"
  /\ absence[e] = "none"
  /\ absence' = [absence EXCEPT ![e] = "waiting"]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prOpen, prStored,
                 prHead, checkState, armed, mergedAs, seenEarlier, historyVars>>

GraceEnds(e) ==
  /\ absence[e] = "waiting"
  /\ absence' = [absence EXCEPT ![e] = "over"]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prOpen, prStored,
                 prHead, checkState, armed, mergedAs, seenEarlier, historyVars>>

ChecksAllowMerge(e) ==
  \/ checkState[e] = "passed"
  \/ (checkState[e] = "absent" /\ absence[e] = "over")
  \/ (checkState[e] = "absent" /\ Break = "absence-counts-drains" /\ seenEarlier[e])
  \/ (checkState[e] \in {"absent", "pending"} /\ Break = "merge-without-checks")

RequestMerge(e) ==
  /\ Mode = "merge"
  /\ Polling
  /\ entryState[e] = "awaiting-merge"
  /\ prStored[e]
  /\ ~armed[e]
  /\ prHead[e] = candidate[e]
  /\ ChecksAllowMerge(e)
  /\ SameTree(Parent(candidate[e]), tip)
  /\ armed' = [armed EXCEPT ![e] = TRUE]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, prOpen, prStored,
                 prHead, checkState, mergedAs, absence, seenEarlier, historyVars>>

ForgeCompletes(e) ==
  LET head     == prHead[e]
      allowed  == checkState[e] \in {"passed", "absent"}
                    \/ (Break = "merge-without-checks" /\ checkState[e] = "pending")
      honoured == /\ head = candidate[e]
                  /\ \/ checkState[e] = "passed"
                     \/ (checkState[e] = "absent" /\ absence[e] = "over")
  IN
  /\ entryState[e] = "awaiting-merge"
  /\ armed[e]
  /\ mergedAs[e] = NoCommit
  /\ (head = candidate[e] \/ Break = "no-match-head-commit")
  /\ allowed
  /\ \E m \in MergeCommits(head, tip) :
       /\ tip' = m
       /\ mergedAs' = [mergedAs EXCEPT ![e] = m]
       /\ trunkRewound' = (trunkRewound \/ tip \notin Ancestors(m))
  /\ publishes' = [publishes EXCEPT ![e] = publishes[e] + 1]
  /\ uncheckedMerge' = (uncheckedMerge \/ ~honoured)
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, prOpen, prStored, prHead,
                 checkState, armed, absence, seenEarlier, checkedAt, staleWrite, droppedCoverage>>

SettleMerged(e) ==
  /\ Polling
  /\ entryState[e] = "awaiting-merge"
  /\ mergedAs[e] # NoCommit
  /\ Landed(e, mergedAs[e])
  /\ paused' = (paused \/ (Break # "no-tree-check" /\ ~SameTree(mergedAs[e], candidate[e])))
  /\ UNCHANGED <<clock, floor, attempt, run, worktree, secondDrain, tip, forgeVars, historyVars>>

BounceOpenPr(e) ==
  /\ Polling
  /\ entryState[e] = "awaiting-merge"
  /\ prStored[e]
  /\ mergedAs[e] = NoCommit
  /\ prHead[e] = candidate[e]
  /\ checkState[e] = "failed"
  /\ Bounced(e)
  /\ prOpen' = [prOpen EXCEPT ![e] = FALSE]
  /\ prStored' = [prStored EXCEPT ![e] = FALSE]
  /\ prHead' = [prHead EXCEPT ![e] = NoCommit]
  /\ checkState' = [checkState EXCEPT ![e] = "absent"]
  /\ armed' = [armed EXCEPT ![e] = FALSE]
  /\ absence' = [absence EXCEPT ![e] = "none"]
  /\ seenEarlier' = [seenEarlier EXCEPT ![e] = FALSE]
  /\ UNCHANGED <<clock, floor, drainVars, tip, mergedAs, historyVars>>

====
