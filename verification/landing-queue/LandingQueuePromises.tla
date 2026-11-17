---- MODULE LandingQueuePromises ----
EXTENDS LandingQueueLeases


NoOverlappingLeases ==
  \A a, b \in Leases :
    a # b /\ InFlight(a) /\ InFlight(b) /\ leaseHolder[a] # leaseHolder[b]
      => ~Overlaps(leasePaths[a], leasePaths[b])

NoStaleWrite == ~staleWrite

OneIntegration == ~secondDrain

LandedIsOnTrunk ==
  \A e \in Entries : entryState[e] = "landed" => landedAs[e] \in Ancestors(tip)

TrunkNeverRewinds == ~trunkRewound

CheckedHeadOnly ==
  /\ ~uncheckedMerge
  /\ \A e \in Entries :
       entryState[e] = "landed" =>
         /\ EntryPrint(e) \in Tree(landedAs[e])
         /\ publishes[e] > 0 =>
              \/ paused
              \/ checkedAt[e] # NoCommit /\ SameTree(landedAs[e], checkedAt[e])

NoStalledEntry ==
  run.pc = "reconciled" =>
    /\ attempt = NoAttempt
    /\ \A e \in Entries : entryState[e] # "landing"

EntryKeepsItsLease ==
  \A e \in Entries :
    entryState[e] \in {"queued", "landing", "awaiting-merge"} => InFlight(entryLease[e])

NoDoubleLanding == \A e \in Entries : publishes[e] <= 1

WidenKeepsCoverage == ~droppedCoverage

====
