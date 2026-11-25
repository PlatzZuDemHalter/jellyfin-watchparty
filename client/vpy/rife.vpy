# Watchparty: wird von mpv als Videofilter geladen (vf=vapoursynth).
# Einstellungen kommen Base64-kodiert über user-data vom Client.
from fractions import Fraction

import vapoursynth as vs
from vapoursynth import core

import wp_rife

cfg = wp_rife.decode(user_data)  # noqa: F821 (von mpv gesetzt)
raw = video_in  # noqa: F821 (echte Bilddauern von mpv)
clip = raw

src = Fraction(int(cfg["src_num"]), int(cfg["src_den"]))
clip = core.std.AssumeFPS(clip, fpsnum=src.numerator, fpsden=src.denominator)

wp_rife.interpolate(clip, cfg, timing=raw).set_output()
