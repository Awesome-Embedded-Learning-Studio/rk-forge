#!/usr/bin/env python3
"""forge progress — live progress bars for long builds (buildroot / kbuild).

Parses the build tool's stdout stream and renders an in-place ANSI progress bar
on stderr (stdout stays clean for piping / logging). Stdlib-only — no rich /
textual dependency, matching the project's no-external-deps discipline
(scripts/fit-pack.py, scripts/rkfw-pack.py).

This is the seed of the Python forge's progress layer (Stage 2 of the TUI plan):
a structured progress engine that's useful even before the rich dashboard
(Stage 3) is wired up. Designed to be wrapped by `forge build` later.

Replay a captured log (demo / regression test):
  python3 scripts/forge/progress.py buildroot document/logs/buildroot-build-*.log
  python3 scripts/forge/progress.py kernel   document/logs/build-kernel.log

Wrap a live build (pipe through):
  make -C third_party/buildroot 2>&1 | python3 scripts/forge/progress.py buildroot
  make -C third_party/src/linux 2>&1 | python3 scripts/forge/progress.py kernel

Total denominator: file replay two-passes the log for an accurate %; stdin/live
is indeterminate (count + rate + ETA-from-rate, no %). Pass --total N to
override (e.g. from a `make -n` dry-run pre-scan).
"""
import argparse
import os
import re
import sys
import time

ESC = '\x1b'
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mK]')


def strip_ansi(s):
    """Strip ANSI color/style escapes (buildroot wraps >>> lines in reverse-video)."""
    return ANSI_RE.sub('', s)


# --------------------------------------------------------------------------- #
# Parsers — one per build tool. Each exposes: feed(line)->bool (was-progress-line),
# .done (completed units), .discovered (units seen), .current (human label).
# --------------------------------------------------------------------------- #

class BuildrootParser:
    """buildroot emits (ANSI reverse-video) `>>> pkg-name  Stage` lines as each
    package moves through Extracting → Patching → Configuring → Building →
    Installing-to-*. Progress unit = distinct packages.

    There is no single reliable "package done" signal (Installing-to-staging is
    mid-life for some packages). The robust signal is rotation: when a NEW package
    name appears, the previous one is done. So .done counts packages rotated past;
    the currently-active package isn't counted as done."""
    name = 'buildroot'
    unit = 'pkgs'
    _re = re.compile(r'^>>>\s+(\S+)\s{2,}(\S.*?)\s*$')

    def __init__(self):
        self.seen = set()
        self.current = None
        self.current_stage = None
        self.done = 0

    def feed(self, line):
        m = self._re.match(strip_ansi(line.rstrip('\n')))
        if not m:
            return False
        pkg, stage = m.group(1), m.group(2)
        if self.current is not None and pkg != self.current:
            self.done += 1  # previous package rotated out → completed
        self.seen.add(pkg)
        self.current, self.current_stage = pkg, stage
        return True

    @property
    def discovered(self):
        return len(self.seen)

    @property
    def current_label(self):
        if not self.current:
            return ''
        return f'{self.current}: {self.current_stage}'


class KernelParser:
    """kbuild emits `  CC path/foo.o` / `  CC [M] drivers/...` / `  LD ...` /
    `  AR ...` / `  AS ...` lines. Progress unit = compile/link/archive steps."""
    name = 'kernel'
    unit = 'units'
    _re = re.compile(r'^\s+(CC|LD|AR|AS)(?:\s\[M\])?\s+(\S+)')

    def __init__(self):
        self.count = 0
        self.last = None

    def feed(self, line):
        m = self._re.match(strip_ansi(line.rstrip('\n')))
        if not m:
            return False
        self.count += 1
        self.last = (m.group(1), m.group(2))
        return True

    @property
    def done(self):
        return self.count

    @property
    def discovered(self):
        return self.count

    @property
    def current_label(self):
        if not self.last:
            return ''
        return f'{self.last[0]} {self.last[1]}'


PARSERS = {'buildroot': BuildrootParser, 'kernel': KernelParser}


# --------------------------------------------------------------------------- #
# Renderer — single-line ANSI bar, updated in place via carriage return.
# Bulletproof (works in any terminal); multi-line dashboard is a future Stage 3.
# --------------------------------------------------------------------------- #

def bar(pct, width):
    filled = int(pct / 100 * width)
    return '█' * filled + '░' * (width - filled)


def fmt_dur(s):
    s = int(s)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def term_width(fallback=120):
    try:
        return os.get_terminal_size(2).columns
    except (OSError, ValueError):
        return fallback


def render_line(parser, total, elapsed, bar_width=28):
    done = parser.done
    cur = parser.current_label
    if total:
        pct = min(done / total * 100, 100.0) if total else 0.0
        rate = done / elapsed if elapsed > 0.3 else 0.0
        rem = max(total - done, 0)
        eta = (rem / rate) if rate else None
        eta_s = fmt_dur(eta) if eta else '--'
        head = f'{bar(pct, bar_width)} {done}/{total} {parser.unit} ({pct:.0f}%) {rate:.1f}/s ETA {eta_s}'
    else:
        rate = done / elapsed if elapsed > 0.3 else 0.0
        head = f'{done} {parser.unit} done  {rate:.1f}/s  elapsed {fmt_dur(elapsed)}'
    line = head + (f' | {cur}' if cur else '')
    cols = term_width()
    if len(line) > cols:
        line = line[:cols - 1] + '…'
    return line


# --------------------------------------------------------------------------- #

def two_pass_total(kind, path):
    """Scan a captured log to get the accurate total (denominator) up front."""
    p = PARSERS[kind]()
    with open(path) as f:
        for line in f:
            p.feed(line)
    return p.discovered


def main():
    ap = argparse.ArgumentParser(description='forge build progress')
    ap.add_argument('kind', choices=['buildroot', 'kernel'])
    ap.add_argument('source', nargs='?', help='log file to replay (default: stdin)')
    ap.add_argument('--total', type=int, help='override total denominator')
    ap.add_argument('--speed', type=float, default=0,
                    help='replay: ms to sleep per line (demo slow-mo)')
    ap.add_argument('--count-only', action='store_true',
                    help="don't render; just count progress units in the input and "
                         "print the total to stdout (for the make -n pre-scan)")
    args = ap.parse_args()

    # Pre-scan mode: feed the whole input through the parser, print the unit
    # count, exit. Used by lib/progress.sh's `make -n | progress.py --count-only`
    # to get the denominator before the real build.
    if args.count_only:
        p = PARSERS[args.kind]()
        src = open(args.source) if args.source else sys.stdin
        try:
            for line in src:
                p.feed(line)
        finally:
            if args.source:
                src.close()
        print(p.discovered)
        return

    is_file = bool(args.source)
    f = open(args.source) if is_file else sys.stdin

    # File replay: two-pass for an accurate total (matches "提前收集" — pre-scan
    # the build set). Live stdin can't pre-scan, so it runs indeterminate unless
    # --total is given (e.g. from a prior `make -n` dry-run).
    total = args.total
    if total is None and is_file:
        total = two_pass_total(args.kind, args.source)
        f.seek(0)

    parser = PARSERS[args.kind]()
    is_tty = sys.stderr.isatty()
    start = time.monotonic()
    last_render = 0.0
    # Non-TTY (CI / redirect / non-interactive): emit periodic snapshot lines so
    # the bar is visible in plain logs, not just one summary at the end. If total
    # is known (file replay / dry-run pre-scan), snapshot every ~5% by events;
    # if indeterminate (live stdin), snapshot every 3s wall-clock.
    if total:
        snap_event_step = max(1, total // 20)
        snap_time_step = 0.0
    else:
        snap_event_step = 0
        snap_time_step = 3.0
    last_snap_done = 0
    last_snap_time = 0.0
    if is_tty:
        sys.stderr.write(ESC + '[?25l')  # hide cursor
        sys.stderr.flush()
    try:
        for line in f:
            hit = parser.feed(line)
            elapsed = time.monotonic() - start
            if hit:
                if is_tty:
                    if (elapsed - last_render) >= 0.1:
                        last_render = elapsed
                        sys.stderr.write('\r' + ESC + '[K' + render_line(parser, total, elapsed))
                        sys.stderr.flush()
                else:
                    fire = (snap_event_step and (parser.done - last_snap_done) >= snap_event_step) or \
                           (snap_time_step and (elapsed - last_snap_time) >= snap_time_step)
                    if fire:
                        if snap_event_step:
                            last_snap_done = parser.done
                        last_snap_time = elapsed
                        sys.stderr.write(render_line(parser, total, elapsed) + '\n')
            if args.speed:
                time.sleep(args.speed / 1000.0)
    finally:
        elapsed = time.monotonic() - start
        if is_tty:
            sys.stderr.write('\r' + ESC + '[K' + render_line(parser, total, elapsed) + '\n')
            sys.stderr.write(ESC + '[?25h')  # show cursor
            sys.stderr.flush()
        else:
            # non-TTY (CI / redirect): one plain final summary line
            sys.stderr.write(render_line(parser, total, elapsed) + '\n')
        if is_file:
            f.close()


if __name__ == '__main__':
    main()
