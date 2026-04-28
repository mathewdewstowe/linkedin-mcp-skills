"""
MCP Skills GitHub Manager
Usage: python main.py [command] [args]

Manages ~/.codex/skills/ ↔ github.com/mathewdewstowe/linkedin-mcp-skills
"""

import sys
import os
import subprocess
from datetime import datetime

SKILLS_ROOT = os.path.expanduser('~/.codex/skills')


def run_git(*args, capture=True):
    """Run a git command in SKILLS_ROOT."""
    cmd = ['git', '-C', SKILLS_ROOT] + list(args)
    result = subprocess.run(cmd, capture_output=capture, text=True)
    return result


def cmd_push(message=None):
    """Commit all changes and push to GitHub."""
    # Check if there's anything to commit
    status = run_git('status', '--porcelain')
    if not status.stdout.strip():
        print('✅ Nothing to commit — already up to date.')
        return

    print('Staging all changes...')
    run_git('add', '-A')

    # Build commit message
    if not message:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        changed = [
            line.strip().split()[-1]
            for line in status.stdout.splitlines()
            if line.strip()
        ]
        # Summarise which skills changed
        skills_changed = set()
        for path in changed:
            parts = path.split('/')
            if parts:
                skills_changed.add(parts[0])
        skills_str = ', '.join(sorted(skills_changed)) or 'skills'
        message = f'update {skills_str} [{timestamp}]'

    print(f'Committing: "{message}"')
    result = run_git('commit', '-m', message)
    if result.returncode != 0:
        print(f'❌ Commit failed:\n{result.stderr}')
        return

    print('Pushing to GitHub...')
    push = run_git('push', 'origin', 'main', capture=False)
    if push.returncode == 0:
        print('✅ Pushed to github.com/mathewdewstowe/linkedin-mcp-skills')
    else:
        print('❌ Push failed. Try: git -C ~/.codex/skills push origin main')


def cmd_pull():
    """Pull latest from GitHub."""
    print('Pulling from GitHub...')
    result = run_git('pull', 'origin', 'main', capture=False)
    if result.returncode == 0:
        print('✅ Up to date.')
    else:
        print('❌ Pull failed.')


def cmd_status():
    """Show uncommitted changes."""
    result = run_git('status')
    print(result.stdout)


def cmd_list():
    """List all skills with their last modified file."""
    skills = sorted([
        d for d in os.listdir(SKILLS_ROOT)
        if os.path.isdir(os.path.join(SKILLS_ROOT, d)) and not d.startswith('.')
    ])
    print(f'{"Skill":<30} {"Last commit"}')
    print('-' * 60)
    for skill in skills:
        log = run_git('log', '--oneline', '-1', '--', skill)
        last = log.stdout.strip() or '(no commits yet)'
        print(f'{skill:<30} {last}')


def cmd_log():
    """Show recent commits."""
    run_git('log', '--oneline', '-20', capture=False)


def print_help():
    print('''
MCP Skills GitHub Manager

USAGE:
  python main.py [command] [message]

COMMANDS:
  push [message]    Commit all changes and push to GitHub
  pull              Pull latest from GitHub
  status            Show uncommitted changes
  list              List all skills with last commit
  log               Show recent commit history

EXAMPLES:
  python main.py push
  python main.py push "add new connector logic"
  python main.py status
  python main.py pull
''')


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'help'

    if command in ['help', '-h', '--help']:
        print_help()
    elif command == 'push':
        message = ' '.join(sys.argv[2:]) or None
        cmd_push(message)
    elif command == 'pull':
        cmd_pull()
    elif command == 'status':
        cmd_status()
    elif command == 'list':
        cmd_list()
    elif command == 'log':
        cmd_log()
    else:
        print(f'❌ Unknown command: {command}')
        print_help()


if __name__ == '__main__':
    main()
