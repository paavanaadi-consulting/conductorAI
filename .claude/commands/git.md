# Git Commands

Run git commands to manage your repository.

## Check Status
```bash
git status
```

## Stage Changes
```bash
git add .
```

## Pull from Current Branch
Automatically detects and pulls from the current branch (not hardcoded to main):
```bash
git pull origin $(git rev-parse --abbrev-ref HEAD)
```

## Commit Code
```bash
git commit -m "Your commit message"
```

## Push to Current Branch
Automatically detects and pushes to the current branch (not hardcoded to main):
```bash
git push origin $(git rev-parse --abbrev-ref HEAD)
```

## Complete Workflow
Pull → Make Changes → Stage → Commit → Push (all on current branch):
```bash
git pull origin $(git rev-parse --abbrev-ref HEAD) && \
git add . && \
git commit -m "Your commit message" && \
git push origin $(git rev-parse --abbrev-ref HEAD)
```

## View Current Branch
```bash
git rev-parse --abbrev-ref HEAD
```

## Notes
- `$(git rev-parse --abbrev-ref HEAD)` dynamically gets the current branch name
- Works on any branch (main, develop, feature branches, etc.)
- No manual branch name specification needed
- Ensure your local branch is tracking a remote branch for seamless push/pull

