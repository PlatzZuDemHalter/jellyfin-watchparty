"""Tests für wp_timing (ohne VapourSynth): python vpy/test_wp_timing.py"""
from fractions import Fraction
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wp_timing  # noqa: E402


def timeline(durations, multi):
    """Zeitstempel der Ausgabebilder so, wie mpv sie aufsummiert."""
    nominal = Fraction(1001, 24000)
    multi = Fraction(multi)
    n_out = int(len(durations) * multi)
    out = []
    t = Fraction(0)
    for k in range(n_out):
        out.append(t)
        i = wp_timing.source_index(k, multi)
        a = durations[min(i, len(durations) - 1)]
        b = durations[min(i + 1, len(durations) - 1)]
        props_a = {"_DurationNum": int(a * 1_000_000), "_DurationDen": 1_000_000}
        props_b = {"_DurationNum": int(b * 1_000_000), "_DurationDen": 1_000_000}
        t += wp_timing.output_duration(
            k, multi, wp_timing.frame_duration(props_a, nominal), wp_timing.frame_duration(props_b, nominal))
    return out


def starts(durations):
    s, t = [], Fraction(0)
    for d in durations:
        s.append(t)
        t += Fraction(int(d * 1_000_000), 1_000_000)
    return s


class Timing(unittest.TestCase):
    def check(self, durations, multi):
        multi = Fraction(multi)
        out = timeline(durations, multi)
        real = starts(durations)
        # Jedes Ausgabebild, das genau auf einem echten Bild liegt, hat dessen echten Zeitstempel
        for k, t in enumerate(out):
            p = Fraction(k) / multi
            if p.denominator == 1 and p < len(durations):
                self.assertEqual(t, real[int(p)], f"Bild {k} (Quelle {p}) weicht ab")
        # Zeitstempel steigen streng
        for a, b in zip(out, out[1:]):
            self.assertGreater(b, a)

    def test_gleichmaessig_ganzzahlig(self):
        self.check([Fraction(1001, 24000)] * 500, 6)

    def test_gleichmaessig_bruch(self):
        self.check([Fraction(1001, 24000)] * 500, Fraction(55, 8))  # 165 Hz

    def test_container_rundet_auf_ms(self):
        # MKV speichert ganze Millisekunden: 42, 42, 41, 42, 42, 41 …
        d = [Fraction(41 + (i % 3 != 2), 1000) for i in range(1000)]
        self.check(d, 6)
        self.check(d, Fraction(5, 2))

    def test_variable_bildrate(self):
        rnd = random.Random(1)
        d = [Fraction(rnd.choice([1001, 1001, 1251, 834]), 30000) for _ in range(800)]
        self.check(d, 6)
        self.check(d, Fraction(17999982, 3000000))

    def test_kein_aufsummierter_fehler(self):
        # Datei behauptet 23,976, ist aber 24,000: früher 1 s Versatz nach ~17 min
        d = [Fraction(1, 24)] * (24 * 60 * 20)
        out = timeline(d, 6)
        self.assertEqual(out[-6], starts(d)[-1])

    def test_kaputte_dauer_nimmt_nennrate(self):
        nominal = Fraction(1, 25)
        self.assertEqual(wp_timing.frame_duration({}, nominal), nominal)
        self.assertEqual(wp_timing.frame_duration({"_DurationNum": -999999, "_DurationDen": 1000000}, nominal), nominal)
        self.assertEqual(wp_timing.frame_duration({"_DurationNum": 5, "_DurationDen": 1}, nominal), nominal)
        self.assertEqual(wp_timing.frame_duration({"_DurationNum": 40000, "_DurationDen": 1000000}, nominal), Fraction(1, 25))


if __name__ == "__main__":
    unittest.main()
