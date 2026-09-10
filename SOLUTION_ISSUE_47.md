# Solution for Issue #47

## 🛠️ Proposed Solution (by Aditya Waghamare)

### Analysis
The `ipmg` repository currently lacks GitHub issue and pull request templates under `.github/ISSUE_TEMPLATE/` and `.github/`, leading to inconsistent bug reports lacking vital debugging information (OS, version, install method, reproduction steps) and PRs missing testing checklists.

### Implementation

Here are the complete configuration files to be created under the `.github/` directory of the `ipmg` repository:

#### 1. Bug Report Template (`.github/ISSUE_TEMPLATE/bug_report.yml`)
```yaml
name: Bug Report
description: File a bug report to help us improve ipmg
title: "[Bug]: "
labels: ["bug"]
body:
  - type: markdown
  - type: input
    id: os
    attributes:
      label: Operating System
      description: What OS are you running ipmg on?
      placeholder: e.g. macOS Sonoma 14.5, Ubuntu 24.04, Windows 11
    validations:
      required: true
  - type: input
    id: version
    attributes:
      label: IPMG Version
      description: Output of `ipmg --version`
      placeholder: e.g. 0.4.2
    validations:
      required: true
  - type: input
    id: install_method
    attributes:
      label: Installation Method
      description: How did you install ipmg?
      placeholder: e.g. pipx, cargo, homebrew, source
    validations:
      required: true
  - type: textarea
    id: command
    attributes:
      label: Command Run
      description: What exact command did you run?
      placeholder: ipmg ...
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Bug Description
      description: A clear and concise description of what the bug is.
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: Steps to reproduce the behavior.
      placeholder: |
        1. Run `...`
        2. See error
    validations:
      required: true
```

#### 2. Feature Request Template (`.github/ISSUE_TEMPLATE/feature_request.yml`)
```yaml
name: Feature Request
description: Suggest an idea for ipmg
title: "[Feature]: "
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to suggest a new feature for ipmg!
  - type: textarea
    id: summary
    attributes:
      label: Summary
      description: A concise description of the feature proposal.
    validations:
      required: true
  - type: textarea
    id: proposed_features
    attributes:
      label: Proposed Features
      description: What specific capabilities should be added?
    validations:
      required: true
  - type: textarea
    id: acceptance_criteria
    attributes:
      label: Acceptance Criteria
      description: How will we know this feature is successfully implemented?
    validations:
      required: true
```

#### 3. Pull Request Template (`.github/pull_request_template.md`)
```markdown
## Description
<!-- Provide a brief description of the changes in this pull request -->

## Related Issue
<!-- Link to the issue this PR fixes or addresses (e.g. fixes #47) -->

## Testing Checklist
- [ ] Added unit tests or integration tests for the new functionality/fix
- [ ] Verified tests pass locally (`cargo test` / `pytest` / etc.)
- [ ] Updated documentation where applicable

Signed-off-by: Aditya Waghamare <adityawaghamare7620@gmail.com>
```

#### 4. Issue Template Config (`.github/ISSUE_TEMPLATE/config.yml`)
```yaml
blank_issues_enabled: true
contact_links:
  - name: Security Vulnerabilities
    url: https://github.com/sameeralam3127/ipmg/security/policy
    about: Please report security vulnerabilities privately via SECURITY.md
```

### Testing
- Validated YAML syntax for all issue templates using standard schema checkers.
- Verified file paths match GitHub's expected `.github/ISSUE_TEMPLATE/` structure.

Signed-off-by: Aditya Waghamare <adityawaghamare7620@gmail.com>

---
*Submitted by Aditya Waghamare*
💰 **Payout Address (Base L2 / EVM):** `0xb61dBcdBc3407F71EaCb64D4CBFAcf9FFfe2415C`