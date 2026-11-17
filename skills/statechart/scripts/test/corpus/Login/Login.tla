---- MODULE Login ----

VARIABLES main
vars == <<main>>

mainStates == {"Locked out", "Reset email sent", "Signed in", "Signed out", "Trying to sign in.Checking first try", "Trying to sign in.Checking last try", "Trying to sign in.Checking second try", "Trying to sign in.Wrong password, 1 try left", "Trying to sign in.Wrong password, 2 tries left"}

TypeOK ==
    /\ main \in mainStates

Init ==
    /\ main = "Signed out"

ThePasswordIsRight ==
    /\ \/ (main = "Trying to sign in.Checking first try" /\ main' = "Signed in")
       \/ (main = "Trying to sign in.Checking second try" /\ main' = "Signed in")
       \/ (main = "Trying to sign in.Checking last try" /\ main' = "Signed in")

ThePasswordIsWrong ==
    /\ \/ (main = "Trying to sign in.Checking first try" /\ main' = "Trying to sign in.Wrong password, 2 tries left")
       \/ (main = "Trying to sign in.Checking second try" /\ main' = "Trying to sign in.Wrong password, 1 try left")
       \/ (main = "Trying to sign in.Checking last try" /\ main' = "Locked out")

YouSubmitAPassword ==
    /\ \/ (main = "Trying to sign in.Wrong password, 2 tries left" /\ main' = "Trying to sign in.Checking second try")
       \/ (main = "Trying to sign in.Wrong password, 1 try left" /\ main' = "Trying to sign in.Checking last try")
       \/ (main = "Signed out" /\ main' = "Trying to sign in.Checking first try")

YouTapForgotPassword ==
    /\ \/ (main = "Trying to sign in.Checking first try" /\ main' = "Reset email sent")
       \/ (main = "Trying to sign in.Wrong password, 2 tries left" /\ main' = "Reset email sent")
       \/ (main = "Trying to sign in.Checking second try" /\ main' = "Reset email sent")
       \/ (main = "Trying to sign in.Wrong password, 1 try left" /\ main' = "Reset email sent")
       \/ (main = "Trying to sign in.Checking last try" /\ main' = "Reset email sent")
       \/ (main = "Locked out" /\ main' = "Reset email sent")

S15MinutesPass ==
    /\ \/ (main = "Locked out" /\ main' = "Signed out")

YouSetANewPassword ==
    /\ \/ (main = "Reset email sent" /\ main' = "Signed out")

YouSignOut ==
    /\ \/ (main = "Signed in" /\ main' = "Signed out")

Next == ThePasswordIsRight \/ ThePasswordIsWrong \/ YouSubmitAPassword \/ YouTapForgotPassword \/ S15MinutesPass \/ YouSetANewPassword \/ YouSignOut

Spec == Init /\ [][Next]_vars

====
