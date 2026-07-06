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
override (e.g. from a `make -n` dry-run pre-scan). NOTE: when passing BOTH a
file and --total, put the file FIRST — `kind FILE --total N` works, but
`kind --total N FILE` hits an argparse quirk (nargs='?' positional after an
option-value) and is rejected as "unrecognized arguments". Stdin/live mode
(the lib/progress.sh helper) passes no file, so this only affects manual demos.
"""
import argparse
import collections
import os
import re
import sys
import time

ESC = '\x1b'
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mK]')


def strip_ansi(s):
    """Strip ANSI color/style escapes (buildroot wraps >>> lines in reverse-video)."""
    return ANSI_RE.sub('', s)


# `make -n` dry-run prints recipe lines verbatim, so the progress marker sits
# INSIDE an `echo '...'` / `echo "..."` argument rather than at line start:
#   kernel dry-run:   set -e;  echo '  CC      init/main.o';  $(CC) ...
#   buildroot dry-run: echo "[7m>>> busybox 1.38.0 Building[27m"
# Extract the echo content so the same regex matches both live (echo output)
# and dry-run (echo command) forms. Best-effort: no echo → line unchanged.
_ECHO_RE = re.compile(r"""echo\s+['"](.+?)['"]""")


def unwrap_recipe(line):
    m = _ECHO_RE.search(line)
    return m.group(1) if m else line


# Error signatures surfaced on exit so the bar doesn't hide make failures.
# Vocabulary mirrors build-uboot.sh's real-error gate (minus its BINMAN_NOISE).
ERR_RE = re.compile(
    r'FATAL ERROR|Lexical error|Syntax error|'
    r'error:|undefined reference|'
    r'cannot find -l|ld returned|'
    r'\*\*\* \[.*\] Error'
)


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
        m = self._re.match(unwrap_recipe(strip_ansi(line.rstrip('\n'))))
        if not m:
            return False
        pkg, stage = m.group(1), m.group(2)
        if self.current is not None and pkg != self.current:
            self.done += 1  # previous package rotated out → completed
        self.seen.add(pkg)
        self.current, self.current_stage = pkg, stage
        return True

    def finalize(self):
        # The active package at clean EOF never rotates (no successor) → count
        # it as done so the bar reaches 100%, not (N-1)/N.
        if self.current is not None:
            self.done += 1
            self.current = None

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
        m = self._re.match(unwrap_recipe(strip_ansi(line.rstrip('\n'))))
        if not m:
            return False
        self.count += 1
        self.last = (m.group(1), m.group(2))
        return True

    def finalize(self):
        pass  # kernel counts on each CC/LD/AR line; no rotation, no off-by-one

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


def render_bar(parser, total, elapsed, log_path='', bar_width=28):
    """Line 1 of the display: the progress bar + count + ETA + the tee'd log path.

    A dry-run --total can UNDERCOUNT a clean build: `make -n` halts at the
    vmlinux link because vmlinux.a is a recipe product dry-run never generates,
    so the post-link CCs it would drive (zImage decompressor, vdso,
    .vmlinux.export, asm-offsets dependents) are never enumerated — ~6% short
    on a clean multi_v7 kernel tree (measured: dry-run 4875 vs real 5196). When
    `done` runs PAST such a total, 'done/total (100%)' with a collapsing ETA
    would mislead, so switch to a 'finalizing post-link' phase that labels the
    tail honestly. (done == total is the normal accurate-100% finish; only the
    strict-over case means the dry-run undercounted.)"""
    done = parser.done
    if total and done > total:
        # Dry-run denominator exhausted — the overrun is the post-link tail the
        # pre-scan couldn't see. Cap the bar at full and label it; no fake ETA.
        rate = done / elapsed if elapsed > 0.3 else 0.0
        head = (f'{bar(100.0, bar_width)} {done} {parser.unit} '
                f'{rate:.1f}/s finalizing post-link (beyond dry-run pre-scan)')
    elif total:
        pct = min(done / total * 100, 100.0)
        rate = done / elapsed if elapsed > 0.3 else 0.0
        rem = max(total - done, 0)
        eta = (rem / rate) if rate else None
        eta_s = fmt_dur(eta) if eta else '--'
        head = f'{bar(pct, bar_width)} {done}/{total} {parser.unit} ({pct:.0f}%) {rate:.1f}/s ETA {eta_s}'
    else:
        rate = done / elapsed if elapsed > 0.3 else 0.0
        head = f'{done} {parser.unit} done  {rate:.1f}/s  elapsed {fmt_dur(elapsed)}'
    if log_path:
        head += f'  log: {log_path}'
    return head


def render_frame(parser, total, elapsed, log_path, last_raw):
    """Two-line display: [bar + ETA + log path] over [latest raw make line].
    The live raw line gives the 'it's alive' flow the bare bar lacked (so the
    bar doesn't feel frozen / ninja-quiet during a long compile); the full
    output is tee'd to log_path by lib/progress.sh for later reference."""
    cols = term_width()
    l1 = render_bar(parser, total, elapsed, log_path)
    if len(l1) > cols:
        l1 = l1[:cols - 1] + '…'
    l2 = ('  ' + last_raw) if last_raw else ''
    if len(l2) > cols:
        l2 = l2[:cols - 1] + '…'
    return l1, l2


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
    ap.add_argument('--log', default='',
                    help="path of the tee'd full build log (shown on the bar line); "
                         "lib/progress.sh sets this when it tees make output to /tmp")
    ap.add_argument('--ignore-errors', default='',
                    help="regex of error signatures to IGNORE (tolerated noise); e.g. "
                         "uboot passes its BINMAN_NOISE so 'Error 103'/'images are "
                         "invalid' don't trigger a false error dump")
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
    # Ringbuffer of recent raw lines + error scan — so a make failure surfaces
    # its error lines instead of being hidden behind the bar (regression fix:
    # without this, the bar freezes at e.g. 30% with the gcc/ld error swallowed).
    recent = collections.deque(maxlen=200)
    saw_error = False
    ignore_re = re.compile(args.ignore_errors) if args.ignore_errors else None
    last_raw = ''
    lines_drawn = 0  # 0 = first frame; 2 = two lines already shown (redraw via cursor-up)
    if is_tty:
        sys.stderr.write(ESC + '[?25l')  # hide cursor
        sys.stderr.flush()
    try:
        for line in f:
            raw = strip_ansi(line.rstrip('\n'))
            recent.append(raw)
            if ERR_RE.search(raw) and not (ignore_re and ignore_re.search(raw)):
                saw_error = True
            if raw.strip():
                last_raw = raw
            parser.feed(line)
            elapsed = time.monotonic() - start
            if is_tty:
                # Refresh on a time throttle (~10fps) so the live raw line keeps
                # flowing — not just on progress hits (otherwise the bar feels
                # frozen during buildroot's slow >>> pkg lines or a silent phase).
                if (elapsed - last_render) >= 0.1:
                    last_render = elapsed
                    l1, l2 = render_frame(parser, total, elapsed, args.log, last_raw)
                    if lines_drawn == 0:
                        sys.stderr.write(l1 + '\n' + l2)
                        lines_drawn = 2
                    else:
                        # cursor-up to line 1, clear both lines, redraw
                        sys.stderr.write(ESC + '[1A\r' + ESC + '[K' + l1 + '\n' + ESC + '[K' + l2)
                    sys.stderr.flush()
            else:
                # Non-TTY (CI / redirect): snapshot on milestones — bar line only
                # (no raw tail) to keep CI logs readable, not line-by-line spam.
                fire = (snap_event_step and (parser.done - last_snap_done) >= snap_event_step) or \
                       (snap_time_step and (elapsed - last_snap_time) >= snap_time_step)
                if fire:
                    if snap_event_step:
                        last_snap_done = parser.done
                    last_snap_time = elapsed
                    sys.stderr.write(render_bar(parser, total, elapsed, args.log) + '\n')
            if args.speed:
                time.sleep(args.speed / 1000.0)
    finally:
        parser.finalize()
        elapsed = time.monotonic() - start
        if is_tty:
            l1, l2 = render_frame(parser, total, elapsed, args.log, last_raw)
            if lines_drawn == 0:
                sys.stderr.write(l1 + '\n' + l2 + '\n')
            else:
                sys.stderr.write(ESC + '[1A\r' + ESC + '[K' + l1 + '\n' + ESC + '[K' + l2 + '\n')
            sys.stderr.write(ESC + '[?25h')  # show cursor
            sys.stderr.flush()
        else:
            # non-TTY (CI / redirect): one plain final summary line
            sys.stderr.write(render_bar(parser, total, elapsed, args.log) + '\n')
        # Surface make failures the bar would otherwise hide: dump the last N
        # raw lines if any matched an error signature.
        if saw_error:
            sys.stderr.write('\n' + '=' * 60 + '\n')
            sys.stderr.write('errors detected during build — last lines:\n')
            for r in recent:
                sys.stderr.write('  ' + r + '\n')
            sys.stderr.write('=' * 60 + '\n')
            sys.stderr.flush()
        if is_file:
            f.close()


if __name__ == '__main__':
    main()
