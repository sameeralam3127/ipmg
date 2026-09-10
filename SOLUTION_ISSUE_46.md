# Solution for Issue #46

## 🛠️ Proposed Solution (by Aditya Waghamare)

### Analysis
The `sameeralam3127/ipmg` repository currently lacks standard open-source contribution guidelines (`CONTRIBUTING.md`) and a Code of Conduct (`CODE_OF_CONDUCT.md`), creating unnecessary friction for new contributors trying to understand setup procedures, test commands, and conventional commit rules.

### Fix
Created comprehensive `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` files adhering to standard open-source best practices (Contributor Covenant) and structured for clarity and ease of onboarding.

### Implementation

#### `CONTRIBUTING.md`
```markdown
# Contributing to ipmg

First off, thank you for taking the time to contribute! 🎉 ipmg is built by the community, for the community.

## Getting Started

### Prerequisites
- Node.js (v18 or higher recommended)
- npm, pnpm, or yarn

### Local Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/your-username/ipmg.git
   cd ipmg
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Run tests to verify your setup:**
   ```bash
   npm test
   ```

## Commit Message Format

This repository adheres to the [Conventional Commits](https://www.conventionalcommits.org/) specification. This convention is enforced to automate releases and changelog generation.

Format: `<type>(<scope>): <subject>`

### Common Types
- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that do not affect the meaning of the code (formatting, semi-colons, etc.)
- **refactor**: A code change that neither fixes a bug nor adds a feature
- **perf**: A code change that improves performance
- **test**: Adding missing tests or correcting existing tests
- **chore**: Changes to the build process or auxiliary tools

Example:
```bash
git commit -m "feat(cli): add support for custom output directories"
```

## How Releases Happen

Releases are fully automated using GitHub Actions and semantic release based on conventional commits. When changes are merged into the default branch:
1. The commit history is analyzed.
2. Semantic versioning (`major.minor.patch`) is automatically calculated.
3. Changelogs are generated and published.
4. Packages are published to the registry.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](./CODE_OF_CONDUCT.md).
```

#### `CODE_OF_CONDUCT.md`
```markdown
# Contributor Covenant Code of Conduct

## Our Pledge

We as members, contributors, and leaders pledge to make participation in our community a harassment-free experience for everyone, regardless of age, body size, visible or invisible disability, ethnicity, sex characteristics, gender identity and expression, level of experience, education, socio-economic status, nationality, personal appearance, race, religion, or sexual identity and orientation.

We pledge to act and interact in ways that contribute to an open, welcoming, diverse, inclusive, and healthy community.

## Our Standards

Examples of behavior that contributes to a positive environment for our community include:
* Demonstrating empathy and kindness toward other people
* Being respectful of differing opinions, viewpoints, and experiences
* Giving and gracefully accepting constructive feedback
* Accepting responsibility and apologizing to those affected by our mistakes, learning from the experience
* Focusing on what is best not just for us as individuals, but for the overall community

Examples of unacceptable behavior include:
* The use of sexualized language or imagery, and sexual attention or advances of any kind
* Trolling, insulting or derogatory comments, and personal or political attacks
* Public or private harassment
* Publishing others' private information, such as a physical or email address, without their explicit permission
* Other conduct which could reasonably be considered inappropriate in a professional setting

## Enforcement

Instances of abusive, harassing, or otherwise unacceptable behavior may be reported to the community leaders responsible for enforcement. All complaints will be reviewed and investigated promptly and fairly.

Project maintainers are responsible for clarifying and enforcing standards of acceptable behavior and will take appropriate and fair corrective action in response to any behavior that they deem inappropriate, threatening, offensive, or harmful.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant](https://www.contributor-covenant.org), version 2.1.
```

### Testing
- Verified Markdown syntax correctness and link integrity.
- Confirmed coverage of development setup, test execution, conventional commits, and release process as requested in issue #46.

Signed-off-by: Aditya Waghamare <adityawaghamare7620@gmail.com>


---
*Submitted by Aditya Waghamare*
💰 **Payout Address (Base L2 / EVM):** `0xb61dBcdBc3407F71EaCb64D4CBFAcf9FFfe2415C`