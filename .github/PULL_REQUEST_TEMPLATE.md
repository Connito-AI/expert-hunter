<!-- One proposal per pull request. Read doc/GUIDE.md first. -->

## Proposal: `exp_...`

**In one sentence:** what the new expert would be good at.

### Checklist

- [ ] I added exactly one directory, `proposals/<name>/`, containing `proposal.yaml` (and optionally a `README.md`) — nothing else in the repo changed.
- [ ] `name` in the file matches the directory name.
- [ ] Every training dataset is public and **not gated** on HuggingFace.
- [ ] I ran the checks locally and they passed:
      `python -m expert_hunter.check <name> --network`
- [ ] The benchmark's scored split is not part of the training data (explained under `contamination`).
- [ ] I have the right to propose these datasets for training (licences listed).

### Anything reviewers should know

<!-- e.g. a custom lm-eval task, a dataset you re-exported, known weaknesses -->

---
**Voting:** give this PR a 👍 (on this description, not on a comment) if you want the subnet to train it. Use the comments to discuss or suggest changes.
