---- MODULE MediaPlayer ----

VARIABLES playback, volume
vars == <<playback, volume>>

playbackStates == {"Buffering", "Paused", "Playing", "Stopped"}
volumeStates == {"Loud", "Muted", "Normal volume"}

TypeOK ==
    /\ playback \in playbackStates
    /\ volume \in volumeStates

Init ==
    /\ playback = "Stopped"
    /\ volume = "Normal volume"

YouPressPlay ==
    /\ \/ (playback = "Stopped" /\ playback' = "Buffering")
       \/ (playback = "Paused" /\ playback' = "Playing")
    /\ UNCHANGED <<volume>>

EnoughDataArrives ==
    /\ \/ (playback = "Buffering" /\ playback' = "Playing")
    /\ UNCHANGED <<volume>>

TheNetworkSlows ==
    /\ \/ (playback = "Playing" /\ playback' = "Buffering")
    /\ UNCHANGED <<volume>>

YouPressPause ==
    /\ \/ (playback = "Playing" /\ playback' = "Paused")
    /\ UNCHANGED <<volume>>

ACallComesIn ==
    /\ (playback \in {"Playing"} \/ volume \in {"Normal volume", "Loud"})
    /\ \/ (playback = "Playing" /\ playback' = "Paused")
       \/ (playback \notin {"Playing"} /\ UNCHANGED playback)
    /\ \/ (volume = "Normal volume" /\ volume' = "Muted")
       \/ (volume = "Loud" /\ volume' = "Muted")
       \/ (volume \notin {"Normal volume", "Loud"} /\ UNCHANGED volume)

TheTrackEnds ==
    /\ (playback \in {"Playing"} \/ volume \in {"Loud"})
    /\ \/ (playback = "Playing" /\ playback' = "Stopped")
       \/ (playback \notin {"Playing"} /\ UNCHANGED playback)
    /\ \/ (volume = "Loud" /\ volume' = "Normal volume")
       \/ (volume \notin {"Loud"} /\ UNCHANGED volume)

YouPressStop ==
    /\ (playback \in {"Playing", "Paused", "Buffering"} \/ volume \in {"Loud"})
    /\ \/ (playback = "Playing" /\ playback' = "Stopped")
       \/ (playback = "Paused" /\ playback' = "Stopped")
       \/ (playback = "Buffering" /\ playback' = "Stopped")
       \/ (playback \notin {"Playing", "Paused", "Buffering"} /\ UNCHANGED playback)
    /\ \/ (volume = "Loud" /\ volume' = "Normal volume")
       \/ (volume \notin {"Loud"} /\ UNCHANGED volume)

YouTurnItUp ==
    /\ \/ (volume = "Normal volume" /\ volume' = "Loud")
    /\ UNCHANGED <<playback>>

YouTurnItDown ==
    /\ \/ (volume = "Loud" /\ volume' = "Normal volume")
    /\ UNCHANGED <<playback>>

YouPressMute ==
    /\ \/ (volume = "Normal volume" /\ volume' = "Muted")
       \/ (volume = "Loud" /\ volume' = "Muted")
       \/ (volume = "Muted" /\ volume' = "Normal volume")
    /\ UNCHANGED <<playback>>

TheCallEnds ==
    /\ \/ (volume = "Muted" /\ volume' = "Normal volume")
    /\ UNCHANGED <<playback>>

Next == YouPressPlay \/ EnoughDataArrives \/ TheNetworkSlows \/ YouPressPause \/ ACallComesIn \/ TheTrackEnds \/ YouPressStop \/ YouTurnItUp \/ YouTurnItDown \/ YouPressMute \/ TheCallEnds

Spec == Init /\ [][Next]_vars

EventuallyStops == <>(playback = "Stopped")

LoudWhenStopped == ~(playback = "Stopped" /\ volume = "Loud")

====
