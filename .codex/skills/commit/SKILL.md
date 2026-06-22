---
name: commit
description: Commit current changes and write commit message
---

# Commit

- Review all uncommitted tracked changes before committing.
- Review untracked files separately and list them explicitly.
- Do not run broad staging commands such as `git add .`, `git add -A`, or `git add --all`.
- Stage files deliberately by path after review.
- Do not add untracked files unless the user explicitly asked for those files to be included.
- Treat generated data, fixtures, exports, cache folders, uploaded files, and large CSV/data folders as excluded unless the user explicitly confirms inclusion.
- Check whether suspicious untracked files are ignored before staging them, and do not force-add ignored files.
- Write a concise commit message with short bullet points for each identified area of changes.
- No need to run black since black is installed as a pre-commit hook.
- Commit the staged changes.
