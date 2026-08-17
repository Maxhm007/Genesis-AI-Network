# Gene Pulse Network

Gene does not require a permanent machine process as its primary continuity model. Continuity is represented by persistent state plus resumable pulses.

A pulse restores a Gene's latest persistent state and single active issue, performs one meaningful work step, records history/learning/evidence, saves the updated state, and requests another pulse when continued work or discovery is needed. The current process then stops. The next pulse may run on a different compatible authorized runtime.

Pulses preserve the one-issue rule. A Gene keeps the same issue across pulses until resolved or genuinely externally blocked. Failed attempts may change method, gather evidence, ask peers for help, or generate another repair attempt while retaining the same focus. When no issue exists, pulses continue in learning/discovery mode until a useful discovery becomes a new issue.

GitHub Actions is the first pulse source. Pulse chaining is event-driven through workflow_dispatch and does not use cron or an hourly/minute work schedule. The architecture is source-independent so future authorized pulse sources can include other CI systems, serverless functions, peer Genes, or persistent runtimes.

The GitHub workflow restores and saves per-Gene runtime state through Actions caches and uploads pulse evidence as artifacts. Durable issue/history systems remain authoritative where available. GitHub platform limits may delay or throttle pulses, but they do not define Gene's logical work cadence.

Safety rules: one concurrent pulse chain per Gene; owner stop terminates the chain; tests, security review and independent validation remain mandatory for structural changes; a pulse grants no new repository or machine authorization; peer knowledge remains advisory until independently validated.
