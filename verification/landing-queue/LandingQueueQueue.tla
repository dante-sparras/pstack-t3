---- MODULE LandingQueueQueue ----
EXTENDS LandingQueueLeases


Submit(e, l, g) ==
  /\ entryState[e] \in {"none", "bounced"}
  /\ entryState[e] = "bounced" => leaseHolder[l] = leaseHolder[entryLease[e]]
  /\ leaseState[l] = "active"
  /\ Live(l)
  /\ EntryPaths(e) \subseteq leasePaths[l]
  /\ (Break = "submit-no-owner-check" \/ OwnerAllowed(leaseHolder[l], g))
  /\ entryState' = [entryState EXCEPT ![e] = "queued"]
  /\ entryLease' = [entryLease EXCEPT ![e] = l]
  /\ leaseState' = [leaseState EXCEPT ![l] = "submitted"]
  /\ staleWrite' = (staleWrite \/ Stale(leaseHolder[l], g))
  /\ UNCHANGED <<leaseHolder, leasePaths, leaseExpiry, clock, floor, candidate,
                 landedAs, drainVars, tip, forgeVars, checkedAt, publishes,
                 droppedCoverage, trunkRewound, uncheckedMerge>>

SubmitDuplicate(e) ==
  /\ entryState[e] \notin {"none", "bounced"}
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, tip, forgeVars, historyVars>>


DrainStart ==
  /\ ~paused
  /\ (Break = "two-integrators" \/ run.pc = "idle")
  /\ secondDrain' = (run.pc # "idle")
  /\ run' = IdleRun("locked")
  /\ seenEarlier' = IF Break = "absence-counts-drains"
                    THEN [e \in Entries |-> seenEarlier[e] \/ absence[e] = "waiting"]
                    ELSE seenEarlier
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, worktree, paused, tip,
                 prOpen, prStored, prHead, checkState, armed, mergedAs, absence, historyVars>>

ReconcileFetch ==
  /\ run.pc = "locked"
  /\ run' = [run EXCEPT !.pc = "fetched", !.fetched = tip]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, worktree, paused,
                 secondDrain, tip, forgeVars, historyVars>>

ReconcileAttempt ==
  LET e          == attempt.entry
      recognised == attempt.cand \in Ancestors(run.fetched)
      settle     == IF Break = "no-already-landed-check" THEN ~recognised ELSE recognised
  IN
  /\ Break # "no-reconcile-attempt"
  /\ run.pc = "fetched"
  /\ attempt # NoAttempt
  /\ attempt' = NoAttempt
  /\ IF settle
     THEN Landed(e, attempt.cand)
     ELSE /\ Requeued(e)
          /\ UNCHANGED <<leaseVars>>
  /\ UNCHANGED <<clock, floor, run, worktree, paused, secondDrain, tip, forgeVars, historyVars>>

ReconcileLanding ==
  /\ run.pc = "fetched"
  /\ (attempt = NoAttempt \/ Break = "no-reconcile-attempt")
  /\ entryState' = [e \in Entries |-> IF entryState[e] = "landing" THEN "queued" ELSE entryState[e]]
  /\ candidate' = [e \in Entries |-> IF entryState[e] = "landing" THEN NoCommit ELSE candidate[e]]
  /\ run' = IdleRun("reconciled")
  /\ UNCHANGED <<leaseVars, clock, floor, entryLease, landedAs, attempt, worktree,
                 paused, secondDrain, tip, forgeVars, historyVars>>

IntegrationReset ==
  /\ run.pc \in {"reconciled", "ready"}
  /\ \E e \in Entries : entryState[e] = "queued"
  /\ (Mode = "merge" => \A e \in Entries : entryState[e] # "awaiting-merge")
  /\ worktree' = tip
  /\ run' = [IdleRun("based") EXCEPT !.base = tip]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, paused, secondDrain,
                 tip, forgeVars, historyVars>>

ApplyRun(e) ==
  LET held == EntryPrint(e) \in Tree(worktree) IN
  /\ run.pc = "based"
  /\ entryState[e] = "queued"
  /\ \/ /\ held
        /\ Break # "no-already-landed-check"
        /\ run' = [run EXCEPT !.pc = "apply-already", !.entry = e]
        /\ UNCHANGED worktree
     \/ /\ (~held \/ Break = "no-already-landed-check")
        /\ \E c \in Replays(worktree) :
             /\ (Change(c) = EntryPrint(e) \/ Break = "no-fingerprint")
             /\ run' = [run EXCEPT !.pc = "apply-ok", !.entry = e, !.cand = c]
             /\ worktree' = c
     \/ /\ ~held
        /\ run' = [run EXCEPT !.pc = "apply-bounce", !.entry = e]
        /\ UNCHANGED worktree
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, paused, secondDrain,
                 tip, forgeVars, historyVars>>

SettleAlready ==
  /\ run.pc = "apply-already"
  /\ Landed(run.entry, run.base)
  /\ run' = IdleRun("ready")
  /\ UNCHANGED <<clock, floor, attempt, worktree, paused, secondDrain, tip, forgeVars, historyVars>>

BounceApply ==
  /\ run.pc = "apply-bounce"
  /\ Bounced(run.entry)
  /\ run' = IdleRun("ready")
  /\ UNCHANGED <<clock, floor, attempt, worktree, paused, secondDrain, tip, forgeVars, historyVars>>

CheckRun ==
  /\ (run.pc = "recorded" \/ (Mode = "merge" /\ run.pc = "apply-ok"))
  /\ \/ /\ run' = [run EXCEPT !.pc = "check-pass"]
        /\ checkedAt' = [checkedAt EXCEPT ![run.entry] = worktree]
     \/ /\ run' = [run EXCEPT !.pc = "check-fail"]
        /\ checkedAt' = [checkedAt EXCEPT ![run.entry] = NoCommit]
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, worktree, paused,
                 secondDrain, tip, forgeVars, publishes, staleWrite, droppedCoverage,
                 trunkRewound, uncheckedMerge>>

BounceCheck ==
  /\ run.pc = "check-fail"
  /\ Bounced(run.entry)
  /\ run' = IdleRun("ready")
  /\ UNCHANGED <<clock, floor, attempt, worktree, paused, secondDrain, tip, forgeVars, historyVars>>


OutsiderPush(c) ==
  /\ c \notin Squashes
  /\ Parent(c) = tip
  /\ tip' = c
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, drainVars, forgeVars, historyVars>>

Crash ==
  /\ run.pc # "idle"
  /\ run' = IdleRun("idle")
  /\ secondDrain' = FALSE
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, worktree, paused, tip,
                 forgeVars, historyVars>>

DrainEnd ==
  /\ Polling
  /\ run' = IdleRun("idle")
  /\ secondDrain' = FALSE
  /\ UNCHANGED <<leaseVars, clock, floor, entryVars, attempt, worktree, paused, tip,
                 forgeVars, historyVars>>

====
