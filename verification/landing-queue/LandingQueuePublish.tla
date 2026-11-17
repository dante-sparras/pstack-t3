---- MODULE LandingQueuePublish ----
EXTENDS LandingQueueBase


RecordLanding ==
  /\ Mode = "publish"
  /\ run.pc = "apply-ok"
  /\ entryState' = [entryState EXCEPT ![run.entry] = "landing"]
  /\ candidate' = [candidate EXCEPT ![run.entry] = run.cand]
  /\ run' = [run EXCEPT !.pc = "recorded"]
  /\ UNCHANGED <<leaseVars, clock, floor, entryLease, landedAs, attempt, worktree,
                 paused, secondDrain, tip, forgeVars, historyVars>>

BeginPublish ==
  /\ Mode = "publish"
  /\ (run.pc = "check-pass" \/ (Break = "ignore-failed-check" /\ run.pc = "check-fail"))
  /\ attempt' = [entry |-> run.entry, cand |-> run.cand]
  /\ run' = [run EXCEPT !.pc = "inserted"]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, worktree, paused, secondDrain,
                 tip, forgeVars, historyVars>>

Publish ==
  /\ run.pc = "inserted"
  /\ (tip = run.base \/ Break = "publish-no-base-check")
  /\ tip' = run.cand
  /\ publishes' = [publishes EXCEPT ![run.entry] = publishes[run.entry] + 1]
  /\ trunkRewound' = (trunkRewound \/ tip \notin Ancestors(run.cand))
  /\ run' = [run EXCEPT !.pc = "pushed"]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, worktree, paused,
                 secondDrain, prOpen, prStored, prHead, checkState, armed, mergedAs,
                 absence, seenEarlier, checkedAt, staleWrite, droppedCoverage, uncheckedMerge>>

PublishRefused ==
  /\ run.pc = "inserted"
  /\ tip # run.base
  /\ Break # "publish-no-base-check"
  /\ run' = [run EXCEPT !.pc = "refused"]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, worktree, paused,
                 secondDrain, tip, forgeVars, historyVars>>

AbandonAttempt ==
  /\ run.pc = "refused"
  /\ attempt' = NoAttempt
  /\ Requeued(run.entry)
  /\ run' = IdleRun("ready")
  /\ UNCHANGED <<leaseVars, clock, floor, worktree, paused, secondDrain, tip, forgeVars, historyVars>>

SettleLanded ==
  /\ CASE Break = "settle-before-publish"        -> run.pc = "inserted"
       [] Break = "lease-released-before-settle" -> run.pc = "released"
       [] OTHER                                  -> run.pc = "pushed"
  /\ attempt' = NoAttempt
  /\ Landed(run.entry, run.cand)
  /\ run' = IdleRun("ready")
  /\ UNCHANGED <<clock, floor, worktree, paused, secondDrain, tip, forgeVars, historyVars>>

ReleaseThenSettle ==
  /\ Break = "lease-released-before-settle"
  /\ run.pc = "pushed"
  /\ leaseState' = [leaseState EXCEPT ![entryLease[run.entry]] = "released"]
  /\ run' = [run EXCEPT !.pc = "released"]
  /\ UNCHANGED <<leaseHolder, leasePaths, leaseExpiry, clock, floor, entryVars,
                 attempt, worktree, paused, secondDrain, tip, forgeVars, historyVars>>

====
