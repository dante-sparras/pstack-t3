---- MODULE LandingQueue ----
EXTENDS LandingQueueBase, LandingQueueLeases, LandingQueueQueue, LandingQueuePublish,
        LandingQueueMerge, LandingQueuePromises


LeaseNext ==
  \/ \E h \in Holders, ps \in SUBSET Paths, ttl \in Ttls, g \in Generations : Claim(h, ps, ttl, g)
  \/ \E l \in Leases, ttl \in Ttls, g \in Generations : Renew(l, ttl, g)
  \/ \E l \in Leases, g \in Generations : Release(l, g)
  \/ \E l \in Leases, ps \in SUBSET Paths, ttl \in Ttls, g \in Generations : Widen(l, ps, ttl, g)
  \/ \E g \in Generations : RaiseFloor(g)
  \/ ClockTick

SmallLeaseNext ==
  \/ \E h \in Holders, ps \in SUBSET Paths, ttl \in Ttls, g \in Generations : Claim(h, ps, ttl, g)
  \/ \E g \in Generations : RaiseFloor(g)
  \/ ClockTick

SharedNext ==
  \/ IF Scope = "all" THEN LeaseNext ELSE SmallLeaseNext
  \/ \E e \in Entries, l \in Leases, g \in Generations : Submit(e, l, g)
  \/ \E e \in Entries : SubmitDuplicate(e)
  \/ DrainStart
  \/ ReconcileFetch
  \/ ReconcileAttempt
  \/ ReconcileLanding
  \/ IntegrationReset
  \/ \E e \in Entries : ApplyRun(e)
  \/ SettleAlready
  \/ BounceApply
  \/ CheckRun
  \/ BounceCheck
  \/ \E c \in Commits : OutsiderPush(c)
  \/ Crash
  \/ DrainEnd

PublishNext ==
  \/ RecordLanding
  \/ BeginPublish
  \/ Publish
  \/ PublishRefused
  \/ AbandonAttempt
  \/ SettleLanded
  \/ ReleaseThenSettle

MergeNext ==
  \/ RecordCandidate
  \/ \E e \in Entries :
       \/ OpenPr(e)
       \/ StorePr(e)
       \/ ChecksPost(e)
       \/ ChecksFinish(e)
       \/ HeadMoves(e)
       \/ AbsenceSeen(e)
       \/ GraceEnds(e)
       \/ RequestMerge(e)
       \/ ForgeCompletes(e)
       \/ SettleMerged(e)
       \/ BounceOpenPr(e)

Next ==
  IF Scope = "leases" THEN LeaseNext
  ELSE IF Mode = "publish" THEN SharedNext \/ PublishNext
  ELSE SharedNext \/ MergeNext

BoundNext == steps < Depth /\ Next /\ steps' = steps + 1

Spec == Init /\ [][BoundNext]_<<View, steps>>

====
