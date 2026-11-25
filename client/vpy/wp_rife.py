"""
Watchparty: RIFE-Zwischenbilder für mpv (über vs-mlrt + TensorRT).

Wird von rife.vpy (in mpv) und build_engine.vpy (vorab die TensorRT-Engine
bauen) benutzt. Beide müssen exakt dieselben Parameter verwenden, sonst baut
TensorRT beim Abspielen eine neue Engine und das Bild hängt minutenlang.
"""
from fractions import Fraction
import base64
import json

import vapoursynth as vs
from vapoursynth import core

import wp_timing

PADDING = {"v4_26": 64, "v4_25_lite": 128, "v4_22_lite": 32}


def decode(data):
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(base64.b64decode(data).decode("utf-8")) if data else {}


def backend(cfg):
    import vsmlrt
    return vsmlrt.Backend.TRT(
        fp16=True,
        output_format=1,
        use_cuda_graph=True,
        num_streams=int(cfg.get("streams", 2)),
        device_id=int(cfg.get("device", 0)),
        static_shape=True,
    )


def padded_size(width, height, model):
    m = PADDING.get(model, 64)
    return (width + m - 1) // m * m, (height + m - 1) // m * m


def interpolate(clip, cfg, timing=None):
    """
    clip:   YUV-Video mit korrekter fps. Gibt YUV im selben Format zurück.
    timing: das Video so, wie mpv es liefert (mit den echten Bilddauern).
            Ohne timing bekommen die Ausgabebilder die Nenn-Bildrate.
    """
    import vsmlrt

    model_key = cfg.get("model", "v4_26")
    model = getattr(vsmlrt.RIFEModel, model_key)
    multi = Fraction(int(cfg["num"]), int(cfg["den"]))
    if multi <= 1:
        return clip

    matrix = cfg.get("matrix", "709")
    rng = cfg.get("range", "limited")
    w, h = clip.width, clip.height
    pw, ph = padded_size(w, h, model_key)

    rgb = core.resize.Bicubic(clip, format=vs.RGBH, matrix_in_s=matrix, range_in_s=rng)
    if (pw, ph) != (w, h):
        rgb = core.std.AddBorders(rgb, right=pw - w, bottom=ph - h)

    # Szenenwechsel erkennen, damit keine Zwischenbilder über Schnitte gerechnet werden
    sc = float(cfg.get("scene", 0.12))
    if sc > 0:
        if hasattr(core, "misc") and hasattr(core.misc, "SCDetect"):
            rgb = core.misc.SCDetect(rgb, threshold=sc)
        elif hasattr(core.std, "SCDetect"):
            rgb = core.std.SCDetect(rgb, threshold=sc)

    out = vsmlrt.RIFE(rgb, multi=multi, model=model, backend=backend(cfg), video_player=True)

    if (pw, ph) != (w, h):
        out = core.std.Crop(out, right=pw - w, bottom=ph - h)

    out = core.resize.Bicubic(out, format=clip.format.id, matrix_s=matrix, range_s=rng)

    # mpv berechnet die Zeitstempel aus _DurationNum/_DurationDen
    fps = Fraction(clip.fps_num, clip.fps_den) * multi
    out = core.std.AssumeFPS(out, fpsnum=fps.numerator, fpsden=fps.denominator)
    if timing is None:
        return core.std.SetFrameProps(out, _DurationNum=fps.denominator, _DurationDen=fps.numerator)
    return real_timestamps(out, timing, multi, nominal=Fraction(clip.fps_den, clip.fps_num))


def real_timestamps(out, src, multi, nominal):
    """
    Gibt jedem Ausgabebild die Dauer, die zu den echten Zeitstempeln der
    Quelle passt (siehe wp_timing). So stimmt der Ton an jedem echten Bild
    wieder exakt, statt sich bis zum nächsten Sprung zu verschieben.
    """
    last = src.num_frames - 1
    base = core.std.BlankClip(src, length=out.num_frames, keep=True)
    # Wie vs-mlrt: FrameEval liefert pro Ausgabebild das passende Quellbild
    left = core.std.FrameEval(base, lambda n: src[min(wp_timing.source_index(n, multi), last)])
    right = core.std.FrameEval(base, lambda n: src[min(wp_timing.source_index(n, multi) + 1, last)])

    def stamp(n, f):
        a = wp_timing.frame_duration(f[1].props, nominal)
        b = wp_timing.frame_duration(f[2].props, nominal)
        d = wp_timing.output_duration(n, multi, a, b)
        res = f[0].copy()
        res.props["_DurationNum"] = d.numerator
        res.props["_DurationDen"] = d.denominator
        return res

    return core.std.ModifyFrame(out, [out, left, right], stamp)
