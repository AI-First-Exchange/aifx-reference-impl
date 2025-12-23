Security Policy
Scope

This repository contains a reference implementation of the AI First Exchange (AIFX) container formats.

The code in this repository is intended to demonstrate:

Packaging of creative works into AIFX containers

Recording of declared provenance and authorship

Cryptographic integrity verification of payload contents

It is not intended to provide:

Digital rights management (DRM)

Content encryption or access control

Copyright enforcement

Identity verification or authentication services

Security Model

The AIFX reference implementation follows a documentation-first security model:

Integrity is enforced through cryptographic hashes (SHA-256)

Metadata is intentionally inspectable and modifiable

Claims of authorship are declared, not adjudicated

Accountability is achieved through transparency and auditability

This model favors verifiability over prevention.

Known Limitations

The following behaviors are by design and should not be reported as vulnerabilities:

Payload files can be extracted from containers

Metadata can be modified if a container is rebuilt

The tools do not prevent false authorship claims

No encryption is applied to container contents

No sandboxing or secure execution environment is provided

These characteristics are intentional and align with AIFX’s philosophy.

Reporting a Vulnerability

If you discover a genuine security issue in the implementation itself (such as code execution, path traversal, or integrity verification bypass), please report it responsibly.

How to Report

Email: security@ai-format.foundation
 (example placeholder — replace with real address)

Subject: [AIFX Security] Brief description

Include:

A clear description of the issue

Steps to reproduce

Impact assessment

Affected files or functions (if known)

Please do not open public GitHub issues for security vulnerabilities.

Supported Versions

Only the latest release on the main branch is supported for security fixes.

Earlier versions may not receive patches.

Disclosure Process

Acknowledge receipt of the report

Assess severity and impact

Develop a fix (if applicable)

Coordinate disclosure timing with the reporter

Publish a patch and advisory if warranted

No Bug Bounty

This project does not currently offer a bug bounty program.

Contributions and responsible disclosures are nonetheless appreciated and acknowledged.

Final Note

AIFX tools are designed to make creative claims transparent, not to make misuse impossible.

Security issues are those that undermine:

Integrity verification

Container correctness

Safe operation of the tooling

Everything else is a matter of policy, provenance, or governance — not software security.
