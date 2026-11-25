"""
Watchparty: echte Zeitstempel für die Zwischenbilder.

Warum: mpv berechnet die Zeitstempel hinter dem VapourSynth-Filter nicht aus
den Eingangsbildern, sondern zählt nur die Dauern (_DurationNum/_DurationDen)
der Ausgabebilder ab dem ersten Bild nach dem letzten Sprung auf. Wenn wir dort
die Nenn-Bildrate der Datei eintragen (z. B. 1/143,86 s), läuft jede kleine
Abweichung der echten Zeitstempel (Rundung im Container, variable Bildrate,
fehlende Bilder in DVD-Rips) bis zum nächsten Sprung immer weiter auf und der
Ton verschiebt sich.

Deshalb bekommt jedes Ausgabebild seine Dauer aus den echten Dauern der beiden
Quellbilder, zwischen denen es liegt. Die Summe ergibt sich dann so, dass an
jedem echten Quellbild der Zeitstempel wieder exakt stimmt. Kleine Fehler
können sich also nicht über mehrere echte Bilder hinweg aufsummieren.

Dieses Modul braucht kein VapourSynth, damit es sich ohne GPU testen lässt.
"""
from fractions import Fraction

# Dauern außerhalb dieses Bereichs sind kaputt oder Sprünge im Stream,
# dann gilt die Nenn-Bildrate.
MIN_DURATION = Fraction(1, 1000)
MAX_DURATION = Fraction(1)


def frame_duration(props, nominal):
    """Echte Dauer eines Quellbilds aus den Eigenschaften, die mpv setzt."""
    try:
        num = int(props["_DurationNum"])
        den = int(props["_DurationDen"])
    except (KeyError, TypeError, ValueError):
        return nominal
    if num <= 0 or den <= 0:
        return nominal
    d = Fraction(num, den)
    if d < MIN_DURATION or d > MAX_DURATION:
        return nominal
    return d


def source_index(k, multi):
    """Quellbild links von Ausgabebild k (wie vs-mlrt: Ausgabe k liegt bei k/multi)."""
    return (k * multi.denominator) // multi.numerator


def output_duration(k, multi, left, right):
    """
    Dauer von Ausgabebild k.

    left:  echte Dauer von Quellbild i = source_index(k, multi)
    right: echte Dauer von Quellbild i + 1

    Ausgabebild k liegt bei Quellposition p = k/multi, also im Quellbild i
    beim Anteil p - i. Seine echte Zeit ist start(i) + (p - i) * left.
    Die Dauer ist der Abstand zur echten Zeit von Bild k + 1. Weil
    start(i + 1) - start(i) = left ist, reichen die beiden Nachbardauern.
    """
    multi = Fraction(multi)
    i = source_index(k, multi)
    here = Fraction(k) / multi - i
    there = Fraction(k + 1) / multi - i
    if there <= 1:
        return (there - here) * left
    return (1 - here) * left + (there - 1) * right
