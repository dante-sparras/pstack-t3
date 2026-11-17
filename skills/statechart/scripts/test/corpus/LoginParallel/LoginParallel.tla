---- MODULE LoginParallel ----

VARIABLES session, wrongTries
vars == <<session, wrongTries>>

sessionStates == {"Checking the password", "Signed in", "Signed out"}
wrongTriesStates == {"1 wrong try", "2 wrong tries", "Locked out", "No wrong tries"}

TypeOK ==
    /\ session \in sessionStates
    /\ wrongTries \in wrongTriesStates

Init ==
    /\ session = "Signed out"
    /\ wrongTries = "No wrong tries"

YouSubmitAPassword ==
    /\ \/ (session = "Signed out" /\ session' = "Checking the password")
    /\ UNCHANGED <<wrongTries>>

ThePasswordIsRight ==
    /\ (session \in {"Checking the password"} \/ wrongTries \in {"1 wrong try", "2 wrong tries"})
    /\ \/ (session = "Checking the password" /\ session' = "Signed in")
       \/ (session \notin {"Checking the password"} /\ UNCHANGED session)
    /\ \/ (wrongTries = "1 wrong try" /\ wrongTries' = "No wrong tries")
       \/ (wrongTries = "2 wrong tries" /\ wrongTries' = "No wrong tries")
       \/ (wrongTries \notin {"1 wrong try", "2 wrong tries"} /\ UNCHANGED wrongTries)

ThePasswordIsWrong ==
    /\ (session \in {"Checking the password"} \/ wrongTries \in {"No wrong tries", "1 wrong try", "2 wrong tries"})
    /\ \/ (session = "Checking the password" /\ session' = "Signed out")
       \/ (session \notin {"Checking the password"} /\ UNCHANGED session)
    /\ \/ (wrongTries = "No wrong tries" /\ wrongTries' = "1 wrong try")
       \/ (wrongTries = "1 wrong try" /\ wrongTries' = "2 wrong tries")
       \/ (wrongTries = "2 wrong tries" /\ wrongTries' = "Locked out")
       \/ (wrongTries \notin {"No wrong tries", "1 wrong try", "2 wrong tries"} /\ UNCHANGED wrongTries)

YouSignOut ==
    /\ \/ (session = "Signed in" /\ session' = "Signed out")
    /\ UNCHANGED <<wrongTries>>

S15MinutesPass ==
    /\ \/ (wrongTries = "Locked out" /\ wrongTries' = "No wrong tries")
    /\ UNCHANGED <<session>>

Next == YouSubmitAPassword \/ ThePasswordIsRight \/ ThePasswordIsWrong \/ YouSignOut \/ S15MinutesPass

Spec == Init /\ [][Next]_vars

SignedInWhileLocked == ~(session = "Signed in" /\ wrongTries = "Locked out")

====
