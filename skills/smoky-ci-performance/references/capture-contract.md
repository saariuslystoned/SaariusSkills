# Capture helper contract

`scripts/capture.py` runs one explicitly approved command once and records the
outcome. It is a measurement utility. It is not a scheduler, test selector,
runner, fleet, or framework.

```text
name and purpose:
  Record argv, streams, exit, monotonic wall time, and optional OS resource
  metrics for one non-interactive command.

usage and subcommands:
  python3 skills/smoky-ci-performance/scripts/capture.py --help
  python3 skills/smoky-ci-performance/scripts/capture.py --version
  python3 skills/smoky-ci-performance/scripts/capture.py \
    --out <new-or-empty-directory> -- <exact argv...>

flags and state changes:
  --out DIR   Required. Create a missing directory. Accept an existing empty
              directory. Refuse a nonempty directory, a symlink, or a file.
              Do not delete, replace, or retry. Acceptance atomically creates
              the empty `.capture-claim` marker inside DIR with exclusive
              creation before execution. A competing caller loses without
              changing the winner's files.
  --          Required. Tokens after it are the exact argv. No shell.
  --help      Usage on stdout, exit 0. Does not run a command.
  --version   Print `capture.py 1` on stdout, exit 0.

  The caller supplies source, config, runtime, and cache context outside this
  helper and owns the environment and any external timeout. The helper has no
  timeout and no process manager. It does not inspect git, the environment,
  credentials, config, or providers, and it does not infer test success from
  output.

stdout schema:
  Child stdout goes only to DIR/stdout.txt. Child stderr goes only to
  DIR/stderr.txt. Stdin is closed. After the stream files are closed, the
  helper writes DIR/capture.json and DIR/summary.md from the same values.
  Successful and failed receipts also reprint capture.json on stdout.
  Usage refusals that do not accept DIR print a bounded error on stderr and
  write no receipt.

  A refused path prints `classification=incomplete` on stderr and writes no
  receipt. The claim marker is a durable reservation: it remains after a
  successful, failed, or interrupted capture, and is therefore treated as a
  stale claim and refused on later use. A command that does not start still
  gets a receipt whose classification is `failure`.

  capture.json (json module, schema smoky-ci-performance.capture.v1):
    classification   complete | failure
    argv             exact argv list
    exit.raw         subprocess return code; negative means a signal; null if
                     the command did not start
    exit.normalized  raw when raw >= 0; 128+signal when raw < 0; null if the
                     command did not start
    exit.signal      signal number, otherwise null
    wall_seconds     monotonic seconds around the single wait; null if the
                     command did not start
    resources.user_seconds / system_seconds
                     waited-child sums from getrusage, or null
    resources.max_rss / max_rss_unit
                     waited-child maximum RSS, or null. Unit is bytes on
                     macOS and KiB on Linux. The value is not a sum and not a
                     process-tree peak. Grandchildren count only when
                     intermediate children waited for them.
    resources.aggregation
                     waited-children when a sample was read, otherwise null
    metrics_supported
                     JSON boolean. False when no resource sample was read.
    cost             the string unknown. No bill or currency is estimated.
    streams          stdout.txt and stderr.txt
    error            null, or {code, message} for a helper failure

  summary.md is one line of `key=json` tokens for classification, exits,
  wall, user, system, max RSS, unit, and cost. Copy those tokens into reports.
  Do not retype them. If a token is null, leave it unknown rather than writing 0.

stderr diagnostics:
  One bounded line. No environment dump and no traceback for expected failures.
  Help warns that argv is recorded exactly and must not contain secrets.

exit codes:
  0              help, version, or a completed command that exited 0
  2              usage, or a refused output path. No command exit exists.
  127            the executable was not found. The receipt classification is
                 failure and its exit fields are null.
  1              the command could not be started, or the receipt could not
                 be written
  command exit   when classification is complete, the helper exits with
                 exit.normalized, including 128+N when the child died by signal
  A receipt is complete only after the process outcome is known and the stream
  files are closed. Invocation failures are nonzero and are never written as
  classification complete.

config/environment precedence:
  Flags only. No config file. The child inherits the caller environment
  unchanged. Nothing from the environment is recorded.

preview and authorization:
  No preview and no retry. Passing argv after -- is the caller's approval to
  run that exact command once. Do not pass secrets in argv.

examples:
  python3 skills/smoky-ci-performance/scripts/capture.py \
    --out ./capture-out -- python3 -c 'print("ok")'

compatibility risks:
  Resource metrics require Python's resource module. Unsupported metrics are
  null, including a real sample whose RSS unit is not known. A measured 0
  stays 0. Earlier waited children of the capture process would be included
  in the sample; the helper waits on only the given command. The caller owns
  deadlines. This helper does not install packages or use the network.
```
