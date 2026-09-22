<!-- One proposal per pull request. doc/GUIDE.md has the short walkthrough. -->

## Proposal: `exp_...`

**In one sentence:** what is trained, on which dataset, to improve which benchmark.

<!-- Optional: anything the YAML didn't have room for — more on your hypothesis,
     a custom lm-eval task (paste its YAML), how a dataset was built, known weaknesses. -->

### Checklist

- [ ] This PR adds exactly **one** file, `proposals/<my-github-login>/exp_<task_name>.yaml`, copied from `template/`, and changes nothing else.
- [ ] `name` matches the file name, and `proposer.github` is my login (the folder name).
- [ ] `hypothesis` says why this data should improve the benchmark; `evidence` lists any support (or `none known`).
- [ ] The benchmark's test split is not part of the training data.

---
**Voting:** give this PR a 👍 (on this description, not on a comment) if you want the subnet to train it. The owner takes the 👍 count into account when choosing the next task. Use the comments to discuss or suggest changes.
