---- MODULE LandingQueueLeases ----
EXTENDS LandingQueueBase


Live(l) == leaseExpiry[l] > clock
InFlight(l) == leaseState[l] = "submitted" \/ (leaseState[l] = "active" /\ Live(l))

Overlaps(a, b) == a \cap b # {}

Clash(h, ps) == \E l \in Leases :
                  InFlight(l) /\ leaseHolder[l] # h /\ Overlaps(leasePaths[l], ps)
Admitted(h, ps) == Break = "no-clash" \/ ~Clash(h, ps)

Stale(h, g) == g < floor /\ PrefixOf(h) = "docs/"
OwnerAllowed(h, g) == Break = "no-owner-check" \/ ~Stale(h, g)

FreeLease == CHOOSE l \in {m \in Leases : leaseState[m] = "free"} :
               \A m \in Leases : leaseState[m] = "free" => l <= m


Claim(h, ps, ttl, g) ==
  /\ ps # {}
  /\ \E l \in Leases : leaseState[l] = "free"
  /\ OwnerAllowed(h, g)
  /\ Admitted(h, ps)
  /\ LET l == FreeLease IN
       /\ leaseState' = [leaseState EXCEPT ![l] = "active"]
       /\ leaseHolder' = [leaseHolder EXCEPT ![l] = h]
       /\ leasePaths' = [leasePaths EXCEPT ![l] = ps]
       /\ leaseExpiry' = [leaseExpiry EXCEPT ![l] = clock + ttl]
  /\ staleWrite' = (staleWrite \/ Stale(h, g))
  /\ UNCHANGED <<clock, floor, entryVars, drainVars, tip, forgeVars, checkedAt,
                 publishes, droppedCoverage, trunkRewound, uncheckedMerge>>

Renew(l, ttl, g) ==
  /\ leaseState[l] = "active"
  /\ OwnerAllowed(leaseHolder[l], g)
  /\ (Live(l) \/ Admitted(leaseHolder[l], leasePaths[l]))
  /\ leaseExpiry' = [leaseExpiry EXCEPT ![l] = clock + ttl]
  /\ staleWrite' = (staleWrite \/ Stale(leaseHolder[l], g))
  /\ UNCHANGED <<leaseState, leaseHolder, leasePaths, clock, floor, entryVars,
                 drainVars, tip, forgeVars, checkedAt, publishes, droppedCoverage,
                 trunkRewound, uncheckedMerge>>

Release(l, g) ==
  /\ leaseState[l] = "active"
  /\ OwnerAllowed(leaseHolder[l], g)
  /\ leaseState' = [leaseState EXCEPT ![l] = "released"]
  /\ staleWrite' = (staleWrite \/ Stale(leaseHolder[l], g))
  /\ UNCHANGED <<leaseHolder, leasePaths, leaseExpiry, clock, floor, entryVars,
                 drainVars, tip, forgeVars, checkedAt, publishes, droppedCoverage,
                 trunkRewound, uncheckedMerge>>

Widen(l, ps, ttl, g) ==
  LET h      == leaseHolder[l]
      folded == {m \in Leases : m # l /\ leaseState[m] = "active" /\ Live(m) /\ leaseHolder[m] = h}
      merged == leasePaths[l] \cup ps \cup UNION {leasePaths[m] : m \in folded}
      own    == IF Live(l) THEN leaseExpiry[l] ELSE clock + ttl
      kept   == IF Break = "widen-drops-live-coverage"
                THEN own
                ELSE Max({own} \cup {leaseExpiry[m] : m \in folded})
  IN
  /\ ps # {}
  /\ leaseState[l] = "active"
  /\ OwnerAllowed(h, g)
  /\ Admitted(h, merged)
  /\ leaseState' = [m \in Leases |-> IF m \in folded THEN "released" ELSE leaseState[m]]
  /\ leasePaths' = [leasePaths EXCEPT ![l] = merged]
  /\ leaseExpiry' = [leaseExpiry EXCEPT ![l] = kept]
  /\ staleWrite' = (staleWrite \/ Stale(h, g))
  /\ droppedCoverage' = (droppedCoverage \/ \E m \in folded : leaseExpiry[m] > kept)
  /\ UNCHANGED <<leaseHolder, clock, floor, entryVars, drainVars, tip, forgeVars,
                 checkedAt, publishes, trunkRewound, uncheckedMerge>>

RaiseFloor(g) ==
  /\ g > floor
  /\ floor' = g
  /\ UNCHANGED <<leaseVars, clock, entryVars, drainVars, tip, forgeVars, historyVars>>

ClockTick ==
  /\ clock < MaxClock
  /\ clock' = clock + 1
  /\ UNCHANGED <<leaseVars, floor, entryVars, drainVars, tip, forgeVars, historyVars>>

====
