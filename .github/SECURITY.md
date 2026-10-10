# Security Policy

## Supported Versions
| Version | Supported |
|---|---|
| latest (`main`) | ✅ |

## Reporting a Vulnerability
Please **do not** open a public issue for security vulnerabilities. Instead,
report them privately:

- Email **edy.cu@live.com**, or
- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) (Security → Report a vulnerability).

You'll get an acknowledgment within 48 hours and a resolution timeline after
triage. Please give us a reasonable window to patch before public disclosure.

## What is tested
`tests/test_boundary.py` asserts that no public route returns a key or token, that the public plan API carries no
raw tool errors, and that the builder-only origin cannot be claimed without the secret token. Plans are stored with a
hashed end-user id; `/verify` shows span names, kinds and durations, never span inputs or outputs.
