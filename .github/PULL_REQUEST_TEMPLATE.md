<!-- One proposal per pull request. Read doc/GUIDE.md first. -->

## Proposal: `exp_...`

**In one sentence:** what the new expert would be good at.

### Checklist

- [ ] This PR adds exactly **one** file, `proposals/<my-github-login>/<task-name>.yaml`, and changes nothing else.
- [ ] The folder is my own GitHub login (the account opening this PR), and `proposer.github` says the same.
- [ ] `name` in the file matches the file name.
- [ ] Every training dataset is public and **not gated** on HuggingFace.
- [ ] I ran the checks locally and they passed:
      `python -m expert_hunter.check <name> --network`
- [ ] The benchmark's scored split is not part of the training data (explained under `contamination`).
- [ ] I have the right to propose these datasets for training (licences listed).

### Anything reviewers should know

<!-- e.g. a custom lm-eval task (paste its YAML here), how a dataset was built, known weaknesses -->

---
**Voting:** give this PR a 👍 (on this description, not on a comment) if you want the subnet to train it. Use the comments to discuss or suggest changes.
